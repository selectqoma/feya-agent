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


async def answer(_):
    return result()


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
                      deliverable="A Markdown comparison")

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
    assert [p["kind"] for p in completed["progress"]] == ["queued", "running", "completed"]
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
        if not task.observations:
            return result("tool", "Inspecting the enquiry", tool="read_case", case_id=case_id)
        assert task.sources
        return result(text=f"This case needs more information [{task.sources[0].id}].", citations=[task.sources[0].id])

    await work.process_event(event_id, read)
    completed = work.task_detail(task["id"])
    assert len(calls) == 2 and completed["status"] == "completed"
    assert completed["sources"][0]["id"] in completed["result_markdown"]
    assert len(completed["usage"]) == 2
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
    assert count == MAX_CALLS
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
    assert "shorter source excerpts" in task["progress"][-1]["content"]
