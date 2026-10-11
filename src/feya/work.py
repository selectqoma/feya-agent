"""Durable conversations and delegated work; model outputs carry no write authority."""

import asyncio
import json
from contextlib import suppress
from datetime import timedelta

from sqlalchemy import select, text, update

from feya import work_db as t
from feya.conversation_models import (
    ConversationAgentInput,
    ConversationAgentResult,
    ConversationCreate,
    ConversationMessage,
    SourceCreate,
    TaskCommand,
)
from feya.db import json_row, scope
from feya.domain import now, uid
from feya.reasoning_errors import ReasoningFailure, classify_failure
from feya.service import Conflict, NotFound

MAX_CALLS = 4
LIFETIME_CALLS = 12
LIFETIME_TOKENS = 420000
LIFETIME_SECONDS = 1080

class ContextBudgetExceeded(ValueError):
    pass


FAILURE = "Reasoning was unavailable or exceeded its work budget. Review the task and resume to retry."


class WorkService:
    def __init__(self, engine, tenant, case_service):
        self.engine, self.tenant, self.case_service = engine, tenant, case_service
        if case_service.tenant != tenant:
            raise ValueError("Case tools must use the same workspace")

    def _lock(self, db):
        # Short transactions serialize sequence assignment and cancellation/result races.
        db.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": f"{self.tenant}:conversation-work"},
        )

    def _row(self, db, table, object_id):
        row = db.execute(select(table).where(scope(table, self.tenant, object_id))).mappings().first()
        if row is None:
            raise NotFound("Object not found in this workspace")
        return dict(row)

    def _rows(self, db, table, *conditions):
        return [
            json_row(r)
            for r in db.execute(
                select(table).where(scope(table, self.tenant), *conditions)
                .order_by(table.c.created_at, table.c.id)
            ).mappings()
        ]

    def _insert(self, db, table, prefix, **values):
        object_id = uid(prefix)
        db.execute(table.insert().values(tenant_id=self.tenant, id=object_id, **values))
        return object_id

    def _update(self, db, table, object_id, **values):
        db.execute(update(table).where(scope(table, self.tenant, object_id)).values(**values))

    def _message(self, db, conversation_id, role, content, *, request_id=None, task_id=None, reply_to=None):
        conversation = self._row(db, t.conversations, conversation_id)
        sequence = conversation["sequence"] + 1
        self._update(db, t.conversations, conversation_id, sequence=sequence)
        message_id = self._insert(
            db, t.messages, "msg", conversation_id=conversation_id, sequence=sequence,
            role=role, content=content, request_id=request_id, task_id=task_id, reply_to=reply_to,
        )
        return message_id, sequence

    def _progress(self, db, task, kind, content):
        self._insert(
            db, t.progress, "progress", task_id=task["id"], generation=task["generation"],
            kind=kind, content=content,
        )

    def create_conversation(self, title="New conversation"):
        title = ConversationCreate(title=title).title.strip()
        if not title:
            raise ValueError("A conversation title is required")
        with self.engine.begin() as db:
            conversation_id = self._insert(db, t.conversations, "conv", title=title, sequence=0)
        return self.detail(conversation_id)

    def list_conversations(self):
        with self.engine.connect() as db:
            return [json_row(r) for r in db.execute(
                select(t.conversations).where(scope(t.conversations, self.tenant))
                .order_by(t.conversations.c.created_at.desc()).limit(100)
            ).mappings()]

    def detail(self, conversation_id):
        with self.engine.connect() as db:
            result = json_row(self._row(db, t.conversations, conversation_id))
            result["messages"] = sorted(
                self._rows(db, t.messages, t.messages.c.conversation_id == conversation_id),
                key=lambda r: r["sequence"],
            )
            result["sources"] = self._rows(db, t.sources, t.sources.c.conversation_id == conversation_id)
            result["tasks"] = self._rows(db, t.tasks, t.tasks.c.conversation_id == conversation_id)
            result["pending"] = len(self._rows(
                db, t.events, t.events.c.conversation_id == conversation_id,
                t.events.c.kind == "chat", t.events.c.processed.is_(False),
            ))
            return result

    def post_message(self, conversation_id, content, request_id):
        message = ConversationMessage(content=content, request_id=request_id)
        if len(content.encode()) > 8000:
            raise ValueError("Messages are limited to 8,000 UTF-8 bytes; attach supporting material separately")
        if not message.content.strip():
            raise ValueError("A message is required")
        with self.engine.begin() as db:
            self._lock(db)
            self._row(db, t.conversations, conversation_id)
            prior = db.execute(select(t.messages).where(
                scope(t.messages, self.tenant), t.messages.c.conversation_id == conversation_id,
                t.messages.c.request_id == message.request_id,
            )).mappings().first()
            if prior:
                if prior["content"] != content:
                    raise Conflict("This request ID was already used for a different message")
                event = db.execute(select(t.events).where(
                    scope(t.events, self.tenant), t.events.c.message_id == prior["id"],
                )).mappings().one()
                return {"message_id": prior["id"], "event_id": event["id"], "deduplicated": True}
            message_id, sequence = self._message(
                db, conversation_id, "user", content, request_id=message.request_id,
            )
            sources = self._source_context(db, conversation_id)
            event_id = self._insert(
                db, t.events, "work", conversation_id=conversation_id, message_id=message_id,
                kind="chat", sequence=sequence, instruction=content, sources=sources, history=[],
            )
        return {"message_id": message_id, "event_id": event_id, "deduplicated": False}

    def _source_context(self, db, conversation_id):
        return [{k: s[k] for k in ("id", "title", "content")} for s in self._rows(
            db, t.sources, t.sources.c.conversation_id == conversation_id,
        )]

    def add_source(self, conversation_id, title, content):
        source = SourceCreate(title=title, content=content)
        if not source.title.strip() or not source.content.strip():
            raise ValueError("Source title and content are required")
        with self.engine.begin() as db:
            self._lock(db)
            self._row(db, t.conversations, conversation_id)
            existing = self._source_context(db, conversation_id)
            if len(existing) >= 8 or len(json.dumps(existing + [source.model_dump()], ensure_ascii=False).encode()) > 14000:
                raise ValueError("Conversation sources are limited to 8 documents and 14,000 UTF-8 bytes including titles")
            source_id = self._insert(
                db, t.sources, "source", conversation_id=conversation_id,
                title=source.title, content=source.content,
            )
            return json_row(self._row(db, t.sources, source_id))

    def list_tasks(self):
        with self.engine.connect() as db:
            return [json_row(r) for r in db.execute(
                select(t.tasks).where(scope(t.tasks, self.tenant))
                .order_by(t.tasks.c.created_at.desc()).limit(100)
            ).mappings()]

    def task_detail(self, task_id):
        with self.engine.connect() as db:
            task = json_row(self._row(db, t.tasks, task_id))
            task["progress"] = self._rows(db, t.progress, t.progress.c.task_id == task_id)
            task["observations"] = [
                observation for event in self._rows(db, t.events, t.events.c.task_id == task_id)
                for observation in event["observations"]
            ]
            task["usage"] = [
                usage for event in self._rows(db, t.events, t.events.c.task_id == task_id)
                for usage in event["usage"]
            ]
            task["limits"] = {
                "calls": LIFETIME_CALLS, "tokens": LIFETIME_TOKENS,
                "active_seconds": LIFETIME_SECONDS, "generation_calls": MAX_CALLS,
            }
            pending = self._rows(db, t.events, t.events.c.task_id == task_id, t.events.c.processed.is_(False))
            task["next_attempt_at"] = pending[-1]["next_attempt_at"] if pending else None
            task["can_resume"] = task["status"] in {"failed", "waiting_for_input"} and (
                task["calls_reserved"] < LIFETIME_CALLS
                and task["tokens_reserved"] + self._minimum_token_reservation() <= LIFETIME_TOKENS
                and task["seconds_reserved"] + 90 <= LIFETIME_SECONDS
            )
            return task

    def _minimum_token_reservation(self):
        from feya.conversation_agent import INSTRUCTIONS, mode_instructions, prompt_for

        request = ConversationAgentInput(mode="task", instruction="x", max_input_tokens=32000)
        return len((INSTRUCTIONS + mode_instructions(request) + prompt_for(request)).encode()) + request.max_output_tokens

    def _queue_task(self, db, task, *, stage="draft"):
        return self._insert(
            db, t.events, "work", conversation_id=task["conversation_id"], task_id=task["id"],
            sequence=task["generation"], generation=task["generation"], kind="task",
            stage=stage, candidate=task["candidate_markdown"] if stage != "draft" else None,
            instruction=task["instruction"], sources=task["sources"], history=task["history"],
        )

    def task_command(self, task_id, command, expected_version, instruction=""):
        request = TaskCommand(expected_version=expected_version, instruction=instruction)
        if command not in {"steer", "cancel", "resume"}:
            raise ValueError("Unknown task command")
        with self.engine.begin() as db:
            self._lock(db)
            task = self._row(db, t.tasks, task_id)
            if request.expected_version != task["version"]:
                raise Conflict("Task changed; refresh before continuing")
            if task["status"] in {"completed", "cancelled"}:
                raise Conflict("This task is already terminal; delegate a new task")
            if command == "steer" and not instruction.strip():
                raise ValueError("Steering requires an instruction")
            if command == "resume" and task["status"] not in {"waiting_for_input", "failed"}:
                raise Conflict("Only paused or failed tasks can resume")
            if command != "cancel" and task["calls_reserved"] >= LIFETIME_CALLS:
                raise Conflict("Task lifetime budget exhausted; delegate a new task after reviewing prior work")
            stage = "draft"
            if command == "resume" and not instruction.strip() and task["candidate_markdown"]:
                stage = "revise" if task["completion_checks"].get("passed") is False else "review"
            history = task["history"]
            if instruction.strip():
                history = (history + [{"role": "user", "content": instruction}])[-10:]
            values = dict(
                status="cancelled" if command == "cancel" else "queued",
                version=task["version"] + 1, generation=task["generation"] + 1,
                instruction=instruction.strip() or task["instruction"], history=history,
                sources=task["sources"] if stage != "draft" else self._source_context(db, task["conversation_id"]),
                error_code="cancelled" if command == "cancel" else None, failure_message="",
                completion_checks=task["completion_checks"] if stage != "draft" else {},
                completion_label=None,
                candidate_markdown=task["candidate_markdown"] if stage != "draft" else "",
            )
            if command != "cancel":
                proposed = task | values
                request = self._input({
                    "task_id": task_id, "kind": "task", "stage": stage,
                    "instruction": proposed["instruction"], "history": proposed["history"],
                    "sources": proposed["sources"], "observations": [],
                    "candidate": proposed["candidate_markdown"] if stage != "draft" else None,
                    "lease_token": None,
                }, proposed)
                if (task["tokens_reserved"] + request.max_input_tokens + request.max_output_tokens > LIFETIME_TOKENS
                        or task["seconds_reserved"] + request.deadline_seconds > LIFETIME_SECONDS):
                    raise Conflict("Task lifetime budget exhausted; delegate a new task after reviewing prior work")
            self._update(db, t.tasks, task_id, **values)
            task.update(values)
            self._progress(db, task, command, instruction.strip() or f"Task {command} requested")
            if command != "cancel":
                self._queue_task(db, task, stage=stage)
            else:
                self._message(db, task["conversation_id"], "assistant", "Task cancelled.", task_id=task_id)
        return self.task_detail(task_id)

    def artifact(self, task_id):
        task = self.task_detail(task_id)
        if task["status"] != "completed" or not task["result_markdown"]:
            raise Conflict("This task has no completed artifact")
        return {
            "task_id": task_id, "filename": f"{task_id}.md", "content_type": "text/markdown",
            "content": task["result_markdown"],
        }

    def _finish(self, db, event, status, content, *, error_code=None):
        self._update(db, t.events, event["id"], processed=True, lease_token=None, lease_until=None)
        if event["task_id"]:
            task = self._row(db, t.tasks, event["task_id"])
            self._update(
                db, t.tasks, task["id"], status=status, version=task["version"] + 1,
                result_markdown=content if status == "completed" else "",
                error_code=error_code, failure_message=content if error_code else "",
            )
            self._progress(db, task, status, content)
        self._message(db, event["conversation_id"], "assistant", content, task_id=event["task_id"], reply_to=event["message_id"])

    def _current(self, db, event):
        if event["processed"]:
            return False
        if event["task_id"]:
            task = self._row(db, t.tasks, event["task_id"])
            if task["generation"] != event["generation"] or task["status"] in {"completed", "cancelled"}:
                self._update(db, t.events, event["id"], processed=True, lease_token=None, lease_until=None)
                return False
        return True

    def _claim(self, event_id):
        with self.engine.begin() as db:
            self._lock(db)
            event = self._row(db, t.events, event_id)
            if not self._current(db, event):
                return None
            if event["kind"] == "chat":
                earlier = db.execute(select(t.events.c.id).where(
                    scope(t.events, self.tenant), t.events.c.conversation_id == event["conversation_id"],
                    t.events.c.kind == "chat", t.events.c.sequence < event["sequence"],
                    t.events.c.processed.is_(False),
                )).first()
                if earlier:
                    return "pending"
            if (event["lease_until"] and event["lease_until"] > now()) or (
                event["next_attempt_at"] and event["next_attempt_at"] > now()
            ):
                return "pending"
            task = self._row(db, t.tasks, event["task_id"]) if event["task_id"] else None
            if event["attempts"] >= MAX_CALLS or (task and task["calls_reserved"] >= LIFETIME_CALLS):
                error = ReasoningFailure("budget_exhausted")
                self._finish(db, event, "failed", error.message, error_code=error.code)
                return None
            if event["kind"] == "chat" and not event["history"]:
                rows = self._rows(db, t.messages, t.messages.c.conversation_id == event["conversation_id"])
                earlier_ids = {r["message_id"] for r in self._rows(
                    db, t.events, t.events.c.conversation_id == event["conversation_id"],
                    t.events.c.kind == "chat", t.events.c.sequence < event["sequence"],
                )}
                event["history"] = [{"role": r["role"], "content": r["content"]} for r in rows
                    if r["id"] in earlier_ids or r["role"] == "assistant"][-10:]
            token = uid("lease")
            event["lease_token"] = token
            try:
                request = self._input(event, task)
            except (ContextBudgetExceeded, ValueError):
                error = ReasoningFailure("context_limit")
                self._finish(db, event, "waiting_for_input", error.message, error_code=error.code)
                return None
            reservation = request.max_input_tokens + request.max_output_tokens
            if task and (task["tokens_reserved"] + reservation > LIFETIME_TOKENS
                         or task["seconds_reserved"] + request.deadline_seconds > LIFETIME_SECONDS):
                error = ReasoningFailure("budget_exhausted")
                self._finish(db, event, "failed", error.message, error_code=error.code)
                return None
            usage = event["usage"] + [{
                "run_id": token, "state": "unknown", "reserved_tokens": reservation,
                "reserved_seconds": request.deadline_seconds,
                "model": None, "input_tokens": None, "output_tokens": None,
            }]
            self._update(
                db, t.events, event_id, attempts=event["attempts"] + 1, lease_token=token,
                lease_until=now() + timedelta(seconds=110), history=event["history"],
                next_attempt_at=None, usage=usage,
            )
            if task:
                self._update(db, t.tasks, task["id"], status="running", version=task["version"] + 1,
                    calls_reserved=task["calls_reserved"] + 1,
                    tokens_reserved=task["tokens_reserved"] + reservation,
                    seconds_reserved=task["seconds_reserved"] + request.deadline_seconds,
                    unknown_usage_calls=task["unknown_usage_calls"] + 1,
                    error_code=None, failure_message="",
                )
                self._progress(db, task, {"review": "reviewing", "revise": "revising"}.get(event["stage"], "running"),
                               f"Reasoning step {event['attempts'] + 1}/{MAX_CALLS}; lifetime {task['calls_reserved'] + 1}/{LIFETIME_CALLS}")
            event["attempts"] += 1
            event["request"] = request
            return event

    def _input(self, event, task=None):
        from feya.conversation_agent import INSTRUCTIONS, mode_instructions, prompt_for

        history = event["history"][-10:]
        assignment = []
        if event["task_id"]:
            task = task or self.task_detail(event["task_id"])
            assignment = [{
                "role": "assistant",
                "content": f"Task objective: {task['objective']}\nRequired deliverable: {task['deliverable']}",
            }]
        while True:
            request = ConversationAgentInput(
                mode="review" if event["stage"] == "review" else event["kind"],
                instruction=event["instruction"], history=history + assignment,
                candidate=event["candidate"] or "",
                review_feedback=[check["detail"][:1500] for check in task["completion_checks"].get("checks", [])
                                 if not check["passed"] and check.get("blocking", True)][:24]
                                if task and event["stage"] == "revise" else [],
                acceptance_criteria=task["acceptance_criteria"] if task else [],
                run_id=event["lease_token"],
                sources=event["sources"], observations=event["observations"],
                max_steps=1, max_input_tokens=32000,
            )
            try:
                prompt = prompt_for(request)
                # UTF-8 bytes are a conservative token reservation, including the fixed instructions.
                request.max_input_tokens = max(1, len((INSTRUCTIONS + mode_instructions(request) + prompt).encode()))
                return request
            except ValueError as exc:
                if not history:
                    raise ContextBudgetExceeded(
                        "This task exceeds the context budget. Resume with a narrower instruction, "
                        "or start a new conversation with shorter source excerpts."
                    ) from exc
                history = history[1:]

    def _tool(self, step):
        if step.tool == "list_cases":
            cases = self.case_service.list_cases(limit=30)
            content = json.dumps([{k: c[k] for k in ("id", "subject", "phase", "next_action")}
                                  for c in cases])
            return {"tool": "list_cases", "content": content[:16000]}, []
        if step.tool == "read_case":
            try:
                case = self.case_service.detail(step.case_id)
            except NotFound:
                return {"tool": "read_case", "case_id": step.case_id, "content": "Case not found in this workspace."}, []
            sources = [{
                "id": e["id"], "title": f"Case evidence: {case['subject']}"[:200],
                "content": json.dumps(e["content"], ensure_ascii=False)[:8000],
            } for e in case["evidence"][-2:]]
            content = json.dumps({
                "id": case["id"], "subject": case["subject"], "phase": case["phase"],
                "summary": case["summary"], "missing": case["missing"],
                "next_action": case["next_action"], "evidence_ids": [s["id"] for s in sources],
                "actions": [{k: a[k] for k in ("id", "capability", "status")} for a in case["actions"][-5:]],
            })
            return {"tool": "read_case", "case_id": step.case_id, "content": content[:16000]}, sources
        raise ValueError("The requested tool is not available")

    def _apply(self, event, result, observation=None, sources=None):
        from feya.completion import validate_completion

        with self.engine.begin() as db:
            self._lock(db)
            current = self._row(db, t.events, event["id"])
            if not self._current(db, current) or current["lease_token"] != event["lease_token"]:
                return False
            step = result.step
            usage = current["usage"]
            known = result.input_tokens is not None and result.output_tokens is not None
            usage[-1] = usage[-1] | {
                "state": "known" if known else "unknown", "model": result.model,
                "input_tokens": result.input_tokens, "output_tokens": result.output_tokens,
            }
            self._update(db, t.events, current["id"], usage=usage)
            task = self._row(db, t.tasks, current["task_id"]) if current["task_id"] else None
            if task and known:
                self._update(db, t.tasks, task["id"], unknown_usage_calls=task["unknown_usage_calls"] - 1)
            if not set(step.citations) <= {s["id"] for s in current["sources"]}:
                raise ReasoningFailure("invalid_output")
            if current["stage"] == "review":
                if not task or step.action != "answer" or step.review is None:
                    raise ReasoningFailure("invalid_output")
                checks = validate_completion(current["candidate"], task["acceptance_criteria"], current["sources"], step.review)
                self._update(db, t.tasks, task["id"], completion_checks=checks, completion_label=checks["label"])
                if checks["passed"]:
                    self._finish(db, current, "completed", current["candidate"])
                elif current["attempts"] + 2 <= MAX_CALLS and task["calls_reserved"] + 2 <= LIFETIME_CALLS:
                    self._update(db, t.events, current["id"], stage="revise", lease_token=None, lease_until=None)
                    self._progress(db, task, "revising", "Review found issues; revising the draft automatically.")
                    return True
                else:
                    self._finish(db, current, "waiting_for_input",
                        "The draft still needs attention and there is no room for another revision and review in this run. "
                        "The candidate and findings are saved; resume to let the agent try again if task budget remains.",
                        error_code="invalid_output")
                return False
            if step.action == "tool":
                combined = {s["id"]: s for s in current["sources"]}
                combined.update({s["id"]: s for s in sources or []})
                if len(combined) > 12:
                    raise ReasoningFailure("context_limit")
                self._update(
                    db, t.events, current["id"], observations=current["observations"] + [observation],
                    sources=list(combined.values()), lease_token=None, lease_until=None,
                )
                if task:
                    self._update(db, t.tasks, task["id"], sources=list(combined.values()))
                    self._progress(db, task, "tool", f"Read {step.tool}")
                return True
            if step.action == "delegate":
                if current["kind"] != "chat" or not step.acceptance_criteria:
                    raise ReasoningFailure("invalid_output")
                task_id = self._insert(
                    db, t.tasks, "task", conversation_id=current["conversation_id"],
                    objective=step.objective, deliverable=step.deliverable,
                    acceptance_criteria=step.acceptance_criteria,
                    instruction=current["instruction"], status="queued", sources=current["sources"],
                    history=current["history"],
                )
                task = self._row(db, t.tasks, task_id)
                self._queue_task(db, task)
                self._progress(db, task, "queued", step.objective)
                self._update(db, t.events, current["id"], processed=True, lease_token=None, lease_until=None)
                self._message(db, current["conversation_id"], "assistant", step.text, task_id=task_id, reply_to=current["message_id"])
            elif task and step.action == "answer":
                # A saved candidate survives worker loss; only its independent review can complete it.
                self._update(db, t.events, current["id"], candidate=step.text, stage="review",
                             lease_token=None, lease_until=None)
                self._update(db, t.tasks, task["id"], candidate_markdown=step.text,
                             completion_checks={}, completion_label=None)
                self._progress(db, task, "candidate_saved", "Draft saved; checking acceptance criteria and evidence.")
                return True
            else:
                self._finish(db, current, "waiting_for_input" if step.action == "need_input" else "completed", step.text)
            return False

    def _fail(self, event, error):
        with self.engine.begin() as db:
            self._lock(db)
            current = self._row(db, t.events, event["id"])
            if not self._current(db, current) or current["lease_token"] != event["lease_token"]:
                return None
            task = self._row(db, t.tasks, current["task_id"]) if current["task_id"] else None
            if error.retryable and current["attempts"] < MAX_CALLS and (not task or task["calls_reserved"] < LIFETIME_CALLS):
                delay = min(45, 5 * 3 ** current["failure_count"])
                self._update(db, t.events, current["id"], lease_token=None, lease_until=None,
                    failure_count=current["failure_count"] + 1, next_attempt_at=now() + timedelta(seconds=delay),
                    error_code=error.code)
                if task:
                    self._update(db, t.tasks, task["id"], status="queued", error_code=error.code,
                                 failure_message=error.message)
                    self._progress(db, task, "retry_scheduled", f"{error.message} Retrying in {delay} seconds.")
                return "pending"
            status = "waiting_for_input" if error.code in {"context_limit", "auth_expired"} else "failed"
            message = error.message
            if error.retryable:
                message += " Automatic retries have stopped. Resume only if task budget remains."
            self._finish(db, current, status, message, error_code=error.code)
            return None

    def _still_current(self, event):
        with self.engine.connect() as db:
            current = self._row(db, t.events, event["id"])
            if current["processed"] or current["lease_token"] != event["lease_token"]:
                return False
            if current["task_id"]:
                task = self._row(db, t.tasks, current["task_id"])
                return task["generation"] == current["generation"] and task["status"] != "cancelled"
            return True

    async def _run(self, event, runner, heartbeat):
        running = asyncio.create_task(runner(event["request"]))
        deadline = asyncio.get_running_loop().time() + event["request"].deadline_seconds
        try:
            while not running.done():
                if asyncio.get_running_loop().time() >= deadline:
                    raise ReasoningFailure("timeout")
                if heartbeat:
                    heartbeat()
                if not self._still_current(event):
                    raise ReasoningFailure("cancelled")
                await asyncio.wait({running}, timeout=0.5)
            return await running
        finally:
            if not running.done():
                running.cancel()
                with suppress(asyncio.CancelledError):
                    await running

    async def process_event(self, event_id, runner, heartbeat=None):
        while True:
            event = self._claim(event_id)
            if event == "pending":
                return "pending"
            if event is None:
                return None
            try:
                result = ConversationAgentResult.model_validate(await self._run(event, runner, heartbeat))
                if result.step.action == "tool":
                    for observed in event["observations"]:
                        same_case = observed.get("case_id") == result.step.case_id
                        if result.step.tool == "read_case" and observed.get("case_id") is None:
                            with suppress(ValueError, AttributeError):
                                same_case = json.loads(observed["content"]).get("id") == result.step.case_id
                        if observed["tool"] == result.step.tool and (result.step.tool == "list_cases" or same_case):
                            raise ReasoningFailure("invalid_output")
                    if event["stage"] == "review":
                        raise ReasoningFailure("invalid_output")
                    observation, sources = self._tool(result.step)
                else:
                    observation, sources = None, None
                if not self._apply(event, result, observation, sources):
                    return None
            except ReasoningFailure as exc:
                return self._fail(event, exc)
            except ContextBudgetExceeded:
                return self._fail(event, ReasoningFailure("context_limit"))
            except ValueError:
                return self._fail(event, ReasoningFailure("invalid_output"))
            except Exception as exc:
                return self._fail(event, classify_failure(exc))
