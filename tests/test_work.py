import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest
from conftest import enquiry
from sqlalchemy import select, update
from sqlalchemy.exc import DBAPIError

from feya import work_db as t
from feya.conversation_models import ConversationAgentResult, ConversationStep
from feya.db import scope
from feya.domain import now, uid
from feya.service import Conflict, NotFound, Service
from feya.work import MAX_CALLS, WorkService


@pytest.fixture
def work(service):
    return WorkService(service.engine, service.tenant, service)


def result(action="answer", text="Prepared the requested summary.", **kwargs):
    return ConversationAgentResult(model="test:work", step=ConversationStep(action=action, text=text, **kwargs))


def reviewed(request, *, passed=True):
    return result(review={
        "criteria": [{"criterion_index": i, "passed": passed, "reason": "Test reviewer assessment"}
                     for i, _ in enumerate(request.acceptance_criteria)],
        "evidence": [{"source_id": source.id, "quote": source.content[:80],
                      "claim": request.candidate[:80]} for source in request.sources
                     if f"[{source.id}]" in request.candidate],
    })


async def answer(request):
    return reviewed(request) if request.mode == "review" else result()


def event_for(work, task_id):
    with work.engine.connect() as db:
        return db.execute(select(t.events.c.id).where(
            scope(t.events, work.tenant), t.events.c.task_id == task_id,
        ).order_by(t.events.c.generation.desc())).scalar()


async def delegate(work, conversation_id=None):
    conversation_id = conversation_id or work.create_conversation("Operations")["id"]
    message = work.post_message(conversation_id, "Prepare a supplier comparison", uid("request"))

    async def plan(_):
        return result("delegate", "I will prepare the comparison.", objective="Compare supplied suppliers",
                      deliverable="A Markdown comparison", acceptance_criteria=["Prepare the requested comparison"])

    await work.process_event(message["event_id"], plan)
    task = work.detail(conversation_id)["tasks"][-1]
    return task, event_for(work, task["id"])


def test_message_idempotency_concurrency_and_workspace_boundaries(work, service):
    conversation = work.create_conversation("Operations")
    with ThreadPoolExecutor(5) as pool:
        responses = list(pool.map(lambda _: work.post_message(conversation["id"], "Hello", "same-request"), range(5)))
    assert len({r["event_id"] for r in responses}) == 1
    assert sum(not r["deduplicated"] for r in responses) == 1
    with pytest.raises(Conflict):
        work.post_message(conversation["id"], "Changed content", "same-request")
    other_cases = Service(service.engine, service.packs, uid("other"))
    other = WorkService(service.engine, other_cases.tenant, other_cases)
    assert other.list_conversations() == []
    with pytest.raises(NotFound):
        other.detail(conversation["id"])
    with pytest.raises(NotFound):
        other.post_message(conversation["id"], "Hello", "new-request")
    with pytest.raises(DBAPIError), work.engine.begin() as db:
        db.execute(t.sources.insert().values(
            tenant_id=other.tenant, id=uid("source"), conversation_id=conversation["id"], title="bad", content="bad",
        ))


async def test_queued_chat_order_and_replay_do_not_duplicate(work):
    conversation = work.create_conversation("Planning")["id"]
    first = work.post_message(conversation, "First question", uid("req"))
    second = work.post_message(conversation, "Second question", uid("req"))
    assert await work.process_event(second["event_id"], answer) == "pending"
    await work.process_event(first["event_id"], answer)
    await work.process_event(first["event_id"], answer)
    seen = []

    async def followup(task):
        seen.extend(m.content for m in task.history)
        return result(text="Second answer")

    await work.process_event(second["event_id"], followup)
    messages = work.detail(conversation)["messages"]
    assert [m["content"] for m in messages if m["role"] == "assistant"] == [
        "Prepared the requested summary.", "Second answer",
    ]
    assert "First question" in seen and "Prepared the requested summary." in seen
    assert "Second question" not in seen
    assert work.detail(conversation)["pending"] == 0
    assert messages[-1]["reply_to"] == second["message_id"]


async def test_delegation_background_result_and_artifact(work):
    task, event_id = await delegate(work)
    assert task["status"] == "queued"
    with pytest.raises(Conflict):
        work.artifact(task["id"])
    # The conversation can answer another question before its delegated task runs.
    message = work.post_message(task["conversation_id"], "What can you do?", uid("req"))
    await work.process_event(message["event_id"], answer)
    await work.process_event(event_id, answer)
    await work.process_event(event_id, answer)
    completed = work.task_detail(task["id"])
    assert completed["status"] == "completed"
    assert work.artifact(task["id"])["content"] == "Prepared the requested summary."
    assert [p["kind"] for p in completed["progress"]] == ["queued", "running", "candidate_saved", "reviewing", "completed"]
    assert len([m for m in work.detail(task["conversation_id"])["messages"] if m["task_id"]]) == 2


async def test_cancel_and_steering_fence_inflight_results(work):
    task, event_id = await delegate(work)
    entered, release = asyncio.Event(), asyncio.Event()

    async def slow(_):
        entered.set()
        await release.wait()
        return result(text="Old result must not publish")

    running = asyncio.create_task(work.process_event(event_id, slow))
    await entered.wait()
    current = work.task_detail(task["id"])
    steered = work.task_command(task["id"], "steer", current["version"], "Focus on delivery times")
    release.set()
    await running
    assert work.task_detail(task["id"])["status"] == "queued"
    assert all("Old result" not in m["content"] for m in work.detail(task["conversation_id"])["messages"])
    with pytest.raises(Conflict):
        work.task_command(task["id"], "cancel", current["version"])
    work.task_command(task["id"], "cancel", steered["version"])
    await work.process_event(event_for(work, task["id"]), answer)
    assert work.task_detail(task["id"])["status"] == "cancelled"
    with pytest.raises(Conflict):
        work.artifact(task["id"])


async def test_missing_input_resume_and_redacted_failure(work):
    task, event_id = await delegate(work)

    async def ask(_):
        return result("need_input", "Please attach the supplier notes.")

    await work.process_event(event_id, ask)
    waiting = work.task_detail(task["id"])
    assert waiting["status"] == "waiting_for_input"
    work.add_source(task["conversation_id"], "Suppliers", "A delivers in two days; B in five days.")
    work.task_command(task["id"], "resume", waiting["version"], "Use the attached notes")
    seen = []

    async def fail(task):
        seen.extend(task.sources)
        raise RuntimeError("SECRET credential error must not leak")

    await work.process_event(event_for(work, task["id"]), fail)
    failed = work.task_detail(task["id"])
    assert seen and failed["status"] == "failed"
    assert "SECRET" not in str(work.detail(task["conversation_id"]))
    assert failed["result_markdown"] == ""


async def test_reserved_calls_bound_crash_recovery(work):
    task, event_id = await delegate(work)
    # Simulate a process disappearing after each persisted reservation, before response storage.
    for number in range(MAX_CALLS):
        event = work._claim(event_id)
        assert event["attempts"] == number + 1
        assert work._claim(event_id) == "pending"
        with work.engine.begin() as db:
            db.execute(update(t.events).where(scope(t.events, work.tenant, event_id)).values(
                lease_until=now() - timedelta(seconds=1),
            ))
    calls = []

    async def forbidden(task):
        calls.append(task)
        return result()

    await work.process_event(event_id, forbidden)
    assert calls == []
    assert work.task_detail(task["id"])["status"] == "failed"


async def test_read_only_tools_and_sources_are_scoped(work, service):
    case_id = service.ingest(enquiry())["case_id"]
    task, event_id = await delegate(work)
    calls = []

    async def read(task):
        calls.append(task)
        if task.mode == "review":
            return reviewed(task)
        if not task.observations:
            return result("tool", "Inspecting the enquiry", tool="read_case", case_id=case_id)
        assert task.sources
        return result(text=f"This case needs more information [{task.sources[0].id}].", citations=[task.sources[0].id])

    await work.process_event(event_id, read)
    completed = work.task_detail(task["id"])
    assert len(calls) == 3 and completed["status"] == "completed"
    assert completed["sources"][0]["id"] in completed["result_markdown"]
    assert len(completed["usage"]) == 3
    assert service.detail(case_id)["actions"] == []
    other_service = Service(service.engine, service.packs, uid("other"))
    foreign_case = other_service.ingest(enquiry())["case_id"]
    observation, sources = work._tool(ConversationStep(
        action="tool", text="Inspect", tool="read_case", case_id=foreign_case,
    ))
    assert sources == [] and "not found" in observation["content"]


async def test_tool_loop_and_invented_citations_never_complete(work):
    task, event_id = await delegate(work)
    count = 0

    async def loop(_):
        nonlocal count
        count += 1
        return result("tool", "Inspecting", tool="list_cases")

    await work.process_event(event_id, loop)
    assert count == 2
    assert work.task_detail(task["id"])["status"] == "failed"
    task, event_id = await delegate(work)

    async def invented(_):
        return result(citations=["evidence_invented"])

    await work.process_event(event_id, invented)
    assert work.task_detail(task["id"])["status"] == "failed"


async def test_context_budget_preserves_instruction_and_source_text(work):
    from feya.conversation_agent import prompt_for

    conversation = work.create_conversation("Long context")["id"]
    source = work.add_source(conversation, "Notes", "a" * 12000)
    with pytest.raises(ValueError, match="14,000 UTF-8 bytes"):
        work.add_source(conversation, "Too much", "b" * 4000)
    with pytest.raises(ValueError, match="UTF-8 bytes"):
        work.post_message(conversation, "🟩" * 3000, uid("req"))
    task, event_id = await delegate(work, conversation)
    instruction = "Preserve this instruction: " + "x" * 3900
    work.task_command(task["id"], "steer", task["version"], instruction)
    event_id = event_for(work, task["id"])
    with work.engine.begin() as db:
        db.execute(update(t.events).where(scope(t.events, work.tenant, event_id)).values(
            history=[{"role": "user", "content": "Historical irrelevant note" * 450}] * 10,
        ))
    seen = []

    async def capture(request):
        prompt_for(request)
        seen.append(request)
        return result(text="Complete")

    await work.process_event(event_id, capture)
    assert seen[0].instruction == instruction
    assert seen[0].sources[0].content == source["content"]
    assert "Task objective:" in seen[0].history[-1].content
    assert len(seen[0].history) < 11
    assert seen[0].max_steps == 1


async def test_oversized_tool_context_pauses_with_actionable_message(work):
    task, event_id = await delegate(work)
    with work.engine.begin() as db:
        db.execute(update(t.events).where(scope(t.events, work.tenant, event_id)).values(
            sources=[{"id": "huge", "title": "Huge", "content": "🟩" * 10000}],
        ))
    await work.process_event(event_id, answer)
    task = work.task_detail(task["id"])
    assert task["status"] == "waiting_for_input"
    assert task["error_code"] == "context_limit"
    assert "shorter source excerpts" in task["progress"][-1]["content"]


@pytest.mark.parametrize("code,retryable,status", [
    ("auth_expired", False, "waiting_for_input"),
    ("rate_limited", True, "queued"),
    ("timeout", True, "queued"),
    ("unavailable", True, "queued"),
    ("invalid_output", False, "failed"),
])
async def test_typed_failures_backoff_and_no_busy_retries(work, code, retryable, status):
    from feya.reasoning_errors import ReasoningFailure

    task, event_id = await delegate(work)
    calls = 0

    async def failing(_):
        nonlocal calls
        calls += 1
        raise ReasoningFailure(code)

    response = await work.process_event(event_id, failing)
    failed = work.task_detail(task["id"])
    assert response == ("pending" if retryable else None)
    assert failed["error_code"] == code and failed["status"] == status
    assert failed["calls_reserved"] == 1 and failed["unknown_usage_calls"] == 1
    await work.process_event(event_id, failing)
    assert calls == 1
    if retryable:
        assert failed["next_attempt_at"]
        with work.engine.begin() as db:
            db.execute(update(t.events).where(scope(t.events, work.tenant, event_id)).values(
                next_attempt_at=now() - timedelta(seconds=1),
            ))
        await work.process_event(event_id, answer)
        completed = work.task_detail(task["id"])
        assert completed["status"] == "completed" and completed["calls_reserved"] == 3


async def test_lifetime_budget_cannot_reset_with_resume_or_steer(work):
    from feya.work import LIFETIME_CALLS

    task, event_id = await delegate(work)

    async def wait(_):
        return result("need_input", "Please clarify the request.")

    for attempt in range(LIFETIME_CALLS):
        await work.process_event(event_id, wait)
        current = work.task_detail(task["id"])
        assert current["calls_reserved"] == attempt + 1
        assert current["seconds_reserved"] == 90 * (attempt + 1)
        if attempt + 1 < LIFETIME_CALLS:
            work.task_command(task["id"], "resume", current["version"], "Clarification supplied")
            event_id = event_for(work, task["id"])
    assert not current["can_resume"]
    with pytest.raises(Conflict, match="lifetime budget"):
        work.task_command(task["id"], "resume", current["version"])
    with pytest.raises(Conflict, match="lifetime budget"):
        work.task_command(task["id"], "steer", current["version"], "Try again")
    assert work.task_command(task["id"], "cancel", current["version"])["status"] == "cancelled"


async def test_cancel_actively_stops_inflight_model_within_one_second(work):
    task, event_id = await delegate(work)
    entered, cancelled = asyncio.Event(), asyncio.Event()

    async def slow(_):
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    running = asyncio.create_task(work.process_event(event_id, slow))
    await entered.wait()
    current = work.task_detail(task["id"])
    work.task_command(task["id"], "cancel", current["version"])
    await asyncio.wait_for(cancelled.wait(), 1)
    await asyncio.wait_for(running, 1)
    final = work.task_detail(task["id"])
    assert final["status"] == "cancelled" and final["calls_reserved"] == 1
    assert final["unknown_usage_calls"] == 1
    assert final["candidate_markdown"] == ""


async def test_saved_candidate_recovery_does_not_regenerate_or_duplicate_artifact(work):
    task, event_id = await delegate(work)
    event = work._claim(event_id)
    assert work._apply(event, result(text="The durable draft")) is True
    assert work.task_detail(task["id"])["candidate_markdown"] == "The durable draft"
    review = work._claim(event_id)
    assert review["request"].mode == "review"
    # A worker died during review; its reserved request remains charged and usage unknown.
    with work.engine.begin() as db:
        db.execute(update(t.events).where(scope(t.events, work.tenant, event_id)).values(
            lease_until=now() - timedelta(seconds=1),
        ))
    modes = []

    async def verify(request):
        modes.append(request.mode)
        assert request.candidate == "The durable draft"
        return reviewed(request)

    await work.process_event(event_id, verify)
    await work.process_event(event_id, verify)
    final = work.task_detail(task["id"])
    assert modes == ["review"]
    assert final["status"] == "completed" and final["calls_reserved"] == 3
    assert final["completion_label"] == "draft_prepared"
    assert work.artifact(task["id"])["content"] == "The durable draft"


async def test_failed_review_attempts_revision_then_preserves_candidate(work):
    task, event_id = await delegate(work)

    async def draft_then_fail_review(request):
        return reviewed(request, passed=False) if request.mode == "review" else result(text="Weak draft")

    await work.process_event(event_id, draft_then_fail_review)
    current = work.task_detail(task["id"])
    assert current["status"] == "waiting_for_input"
    assert current["completion_label"] == "needs_revision"
    assert current["candidate_markdown"] == "Weak draft" and current["result_markdown"] == ""
    assert not current["completion_checks"]["passed"]
    with pytest.raises(Conflict):
        work.artifact(task["id"])
    work.task_command(task["id"], "resume", current["version"])

    async def improve(request):
        if request.mode == "task":
            assert request.candidate == "Weak draft" and request.review_feedback
        return await answer(request)

    await work.process_event(event_for(work, task["id"]), improve)
    final = work.task_detail(task["id"])
    assert final["status"] == "completed" and final["calls_reserved"] == 6


async def test_candidate_survives_generation_budget_and_resume_only_reviews(work):
    task, event_id = await delegate(work)
    calls = 0

    async def slow_draft(request):
        nonlocal calls
        calls += 1
        if calls < MAX_CALLS:
            return result("tool", "Reading cases", tool="read_case", case_id=f"missing_case_{calls}")
        return result(text="Saved at the last available call")

    await work.process_event(event_id, slow_draft)
    current = work.task_detail(task["id"])
    assert current["error_code"] == "budget_exhausted"
    assert current["candidate_markdown"] and current["result_markdown"] == ""
    work.task_command(task["id"], "resume", current["version"])
    modes = []

    async def review_only(request):
        modes.append(request.mode)
        return reviewed(request)

    await work.process_event(event_for(work, task["id"]), review_only)
    final = work.task_detail(task["id"])
    assert modes == ["review"] and final["calls_reserved"] == MAX_CALLS + 1
    assert final["status"] == "completed"


async def test_reserved_usage_known_receipts_and_duplicate_worker_fencing(work):
    task, event_id = await delegate(work)
    entered, release = asyncio.Event(), asyncio.Event()

    async def measured(request):
        entered.set()
        await release.wait()
        return (reviewed(request) if request.mode == "review" else result()).model_copy(
            update={"input_tokens": 100, "output_tokens": 50},
        )

    running = asyncio.create_task(work.process_event(event_id, measured))
    await entered.wait()
    assert await work.process_event(event_id, measured) == "pending"
    release.set()
    await running
    final = work.task_detail(task["id"])
    assert final["calls_reserved"] == 2 and final["unknown_usage_calls"] == 0
    assert final["tokens_reserved"] < 2 * 35000
    assert all(receipt["state"] == "known" for receipt in final["usage"])
    assert final["tokens_reserved"] == sum(u["reserved_tokens"] for u in final["usage"])


@pytest.mark.parametrize("field,value", [("tokens_reserved", 419999), ("seconds_reserved", 1000)])
async def test_resume_and_steer_enforce_all_lifetime_budgets(work, field, value):
    task, event_id = await delegate(work)

    async def ask(_):
        return result("need_input", "Please clarify.")

    await work.process_event(event_id, ask)
    with work.engine.begin() as db:
        db.execute(update(t.tasks).where(scope(t.tasks, work.tenant, task["id"])).values(**{field: value}))
    current = work.task_detail(task["id"])
    assert not current["can_resume"]
    for command in ("resume", "steer"):
        with pytest.raises(Conflict, match="lifetime budget"):
            work.task_command(task["id"], command, current["version"], "Try again")
    assert work.task_detail(task["id"])["generation"] == current["generation"]


async def test_worker_stops_repeated_missing_case_lookup(work):
    task, event_id = await delegate(work)
    tool_calls = []
    original = work._tool

    def capture(step):
        tool_calls.append(step.case_id)
        return original(step)

    work._tool = capture

    async def repeat(_):
        return result("tool", "Reading", tool="read_case", case_id="nonexistent_case")

    await work.process_event(event_id, repeat)
    assert tool_calls == ["nonexistent_case"]
    final = work.task_detail(task["id"])
    assert final["error_code"] == "invalid_output"
    assert final["observations"][0]["case_id"] == "nonexistent_case"


async def test_worker_http_classifies_error_and_forwards_cancel(work, service, monkeypatch):
    import httpx

    from feya import worker

    entered, cancelled = asyncio.Event(), asyncio.Event()
    mode = "error"
    requests = []

    async def handle(request):
        requests.append(request.url.path)
        if request.url.path.startswith("/conversation/cancel/"):
            cancelled.set()
            return httpx.Response(200, json={"cancelled": True})
        if mode == "error":
            return httpx.Response(503, json={"detail": {
                "code": "auth_expired", "message": "SECRET do not display", "retryable": True,
            }})
        entered.set()
        await asyncio.Event().wait()

    original_client = httpx.AsyncClient
    monkeypatch.setattr(worker.httpx, "AsyncClient", lambda **kwargs: original_client(
        transport=httpx.MockTransport(handle), **kwargs,
    ))
    monkeypatch.setattr(worker.activity, "heartbeat", lambda: None)
    activities = worker.Activities(service)
    task, event_id = await delegate(work)
    await activities.process_work(event_id)
    current = work.task_detail(task["id"])
    assert current["error_code"] == "auth_expired"
    assert "SECRET" not in current["failure_message"]
    mode = "slow"
    work.task_command(task["id"], "resume", current["version"])
    running = asyncio.create_task(activities.process_work(event_for(work, task["id"])))
    await asyncio.wait_for(entered.wait(), 2)
    current = work.task_detail(task["id"])
    work.task_command(task["id"], "cancel", current["version"])
    await asyncio.wait_for(cancelled.wait(), 2)
    await asyncio.wait_for(running, 2)
    assert sum(path.startswith("/conversation/cancel/") for path in requests) == 1


async def test_agent_revises_from_persisted_review_feedback_without_user_input(work):
    task, event_id = await delegate(work)
    draft = work._claim(event_id)
    assert work._apply(draft, result(text="Incomplete comparison"))
    review_event = work._claim(event_id)
    assert work._apply(review_event, reviewed(review_event["request"], passed=False))
    assert work.task_detail(task["id"])["status"] == "running"
    # A replacement worker picks up the committed repair without rerunning the first draft.
    resumed = WorkService(work.engine, work.tenant, work.case_service)
    modes = []

    async def repair(request):
        modes.append(request.mode)
        if request.mode == "task":
            assert request.candidate == "Incomplete comparison"
            assert request.review_feedback and "Test reviewer assessment" in request.review_feedback[0]
            assert request.instruction == "Prepare a supplier comparison"
            return result(text="Revised complete comparison")
        assert request.candidate == "Revised complete comparison"
        assert request.review_feedback == []
        return reviewed(request)

    await resumed.process_event(event_id, repair)
    await resumed.process_event(event_id, repair)
    final = resumed.task_detail(task["id"])
    assert modes == ["task", "review"]
    assert final["status"] == "completed" and final["calls_reserved"] == 4
    assert resumed.artifact(task["id"])["content"] == "Revised complete comparison"
    assert sum(p["kind"] == "completed" for p in final["progress"]) == 1


async def test_review_notes_do_not_spend_extra_calls_or_ask_operator(work):
    task, event_id = await delegate(work)
    with work.engine.begin() as db:
        db.execute(update(t.events).where(scope(t.events, work.tenant, event_id)).values(
            sources=[{"id": "src_note", "title": "Note", "content": "Payment within 30 days."}],
        ))

    async def draft(request):
        if request.mode == "review":
            return result(review={"criteria": [{"criterion_index": 0, "passed": True,
                                                 "reason": "Substantively complete."}],
                                  "evidence": [{"source_id": "src_note", "quote": "Payment: 30 days",
                                                "claim": "Pay within thirty days"}]})
        return result(text="Pay within thirty days [src_note].", citations=["src_note"])

    await work.process_event(event_id, draft)
    final = work.task_detail(task["id"])
    assert final["status"] == "completed" and final["calls_reserved"] == 2
    assert any(not check["passed"] and not check["blocking"] for check in final["completion_checks"]["checks"])


@pytest.mark.parametrize("after_revision", [False, True])
async def test_malformed_review_resume_preserves_candidate_and_source_snapshot(work, after_revision):
    from feya.reasoning_errors import ReasoningFailure

    task, event_id = await delegate(work)
    draft = work._claim(event_id)
    work._apply(draft, result(text="Original comparison"))
    if after_revision:
        review = work._claim(event_id)
        work._apply(review, reviewed(review["request"], passed=False))
        revision = work._claim(event_id)
        work._apply(revision, result(text="Revised comparison"))
    review = work._claim(event_id)
    candidate = review["request"].candidate
    work._fail(review, ReasoningFailure("invalid_output"))
    failed = work.task_detail(task["id"])
    assert failed["completion_checks"] == {}
    work.add_source(task["conversation_id"], "New notes", "Added after the saved draft")
    work.task_command(task["id"], "resume", failed["version"])
    modes = []

    async def review_only(request):
        modes.append(request.mode)
        assert request.candidate == candidate
        assert request.sources == review["request"].sources
        assert request.review_feedback == []
        return reviewed(request)

    await work.process_event(event_for(work, task["id"]), review_only)
    final = work.task_detail(task["id"])
    assert modes == ["review"]
    assert final["status"] == "completed"
    assert final["calls_reserved"] == failed["calls_reserved"] + 1
    assert work.artifact(task["id"])["content"] == candidate
