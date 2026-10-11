import asyncio
from dataclasses import replace

import httpx
import pytest
from pydantic_ai.exceptions import ModelHTTPError, UnexpectedModelBehavior, UsageLimitExceeded

from feya import agents
from feya.reasoning_errors import ReasoningFailure, classify_failure


@pytest.mark.parametrize(("error", "code", "retryable"), [
    (ModelHTTPError(401, "test", "SECRET"), "auth_expired", False),
    (ModelHTTPError(403, "test", "SECRET"), "auth_expired", False),
    (ModelHTTPError(429, "test", "SECRET"), "rate_limited", True),
    (ModelHTTPError(503, "test", "SECRET"), "unavailable", True),
    (httpx.ConnectError("SECRET"), "unavailable", True),
    (TimeoutError("SECRET"), "timeout", True),
    (UnexpectedModelBehavior("SECRET"), "invalid_output", False),
    (UsageLimitExceeded("SECRET"), "budget_exhausted", False),
    (RuntimeError("SECRET"), "internal_error", False),
    (ReasoningFailure("context_limit"), "context_limit", False),
])
def test_failure_classification_is_safe_and_actionable(error, code, retryable):
    failure = classify_failure(error)
    assert failure.code == code and failure.retryable is retryable
    assert "SECRET" not in str(failure.as_dict())
    assert failure.message


def app_for(monkeypatch, runner):
    monkeypatch.setattr(agents, "settings", replace(agents.settings, agent_token="test-worker"))
    monkeypatch.setattr(agents, "make_runner", agents.FixtureRunner)
    monkeypatch.setattr(agents, "make_conversation_runner", lambda: runner)
    return agents.create_agent_app()


async def test_endpoint_returns_failure_category_without_provider_body(monkeypatch):
    class Runner:
        async def run(self, _):
            raise ModelHTTPError(401, "test", "SECRET provider credential and customer prompt")

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app_for(monkeypatch, Runner())),
        base_url="http://test", headers={"Authorization": "Bearer test-worker"},
    ) as client:
        response = await client.post("/conversation/run", json={"mode": "chat", "instruction": "Hello"})
        assert response.status_code == 422
        assert response.json()["detail"]["code"] == "auth_expired"
        assert "SECRET" not in response.text


async def test_active_and_late_cancellation_and_duplicate_ids(monkeypatch):
    entered, stopped = asyncio.Event(), asyncio.Event()
    calls = []

    class Runner:
        async def run(self, task):
            calls.append(task.run_id)
            entered.set()
            try:
                await asyncio.Event().wait()
            finally:
                stopped.set()

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app_for(monkeypatch, Runner())),
        base_url="http://test", headers={"Authorization": "Bearer test-worker"},
    ) as client:
        body = {"mode": "chat", "instruction": "Hello", "run_id": "lease_active"}
        running = asyncio.create_task(client.post("/conversation/run", json=body))
        await asyncio.wait_for(entered.wait(), 2)
        assert (await client.post("/conversation/run", json=body)).status_code == 409
        assert (await client.post("/conversation/cancel/lease_active", headers={"Authorization": "wrong"})).status_code == 401
        cancelled = await client.post("/conversation/cancel/lease_active")
        assert cancelled.json()["cancellation_requested"]
        response = await asyncio.wait_for(running, 2)
        assert response.status_code == 499 and stopped.is_set()
        await client.post("/conversation/cancel/lease_late")
        late = await client.post("/conversation/run", json=body | {"run_id": "lease_late"})
        assert late.status_code == 499
        assert calls == ["lease_active"]


async def test_queue_time_counts_toward_deadline(monkeypatch):
    calls = []

    class Runner:
        async def run(self, task):
            calls.append(task.run_id)
            await asyncio.Event().wait()

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app_for(monkeypatch, Runner())),
        base_url="http://test", headers={"Authorization": "Bearer test-worker"},
    ) as client:
        responses = await asyncio.gather(*[client.post("/conversation/run", json={
            "mode": "chat", "instruction": "Hello", "run_id": f"lease_{i}", "deadline_seconds": 1,
        }) for i in range(3)])
        assert all(r.json()["detail"]["code"] == "timeout" for r in responses)
        assert len(calls) == 2
