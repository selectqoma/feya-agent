import asyncio
import json
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient
from pydantic_ai import Agent
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.models.test import TestModel

from feya import agents, conversation_agent
from feya.completion import validate_completion
from feya.conversation_agent import (
    ConversationClaudeRunner,
    ConversationFixtureRunner,
    ConversationPydanticRunner,
)
from feya.conversation_models import (
    ConversationAgentInput,
    ConversationStep,
    ToolObservation,
    WorkSource,
)


def make_runner(**output):
    runner = object.__new__(ConversationPydanticRunner)
    runner.model = "test:conversation"
    runner.agent = Agent(TestModel(custom_output_args=output), output_type=ConversationStep)
    return runner


async def test_structured_answer_cites_supplied_sources_and_records_usage():
    task = ConversationAgentInput(
        mode="task", instruction="Summarize our payment terms",
        sources=[WorkSource(id="src_terms", title="Terms", content="Payment within 30 days.")],
    )
    result = await make_runner(
        action="answer", text="Payment is due within 30 days. [src_terms]", citations=["src_terms"]
    ).run(task)
    assert result.step.citations == ["src_terms"]
    assert result.input_tokens > 0
    assert result.output_tokens > 0


async def test_unused_null_criteria_from_provider_normalizes_without_repair_call():
    result = await make_runner(action="answer", text="Revenue is income before costs.",
                               acceptance_criteria=None).run(
        ConversationAgentInput(mode="chat", instruction="Explain revenue", max_steps=1)
    )
    assert result.step.acceptance_criteria == []
    assert result.step.action == "answer"


async def test_unknown_citations_and_recursive_delegation_are_rejected():
    task = ConversationAgentInput(mode="task", instruction="Prepare report")
    with pytest.raises(ValueError, match="unavailable source"):
        await make_runner(action="answer", text="Invented claim", citations=["src_fake"]).run(task)
    with pytest.raises(ValueError, match="recursively"):
        await make_runner(
            action="delegate", text="Delegate again", objective="Report", deliverable="Report"
        ).run(task)


async def test_context_budget_rejects_before_model_execution():
    task = ConversationAgentInput(mode="chat", instruction="Hello", max_input_tokens=1)
    with pytest.raises(ValueError, match="context limit"):
        await make_runner(action="answer", text="Hi").run(task)


async def test_task_mode_explains_execution_and_local_artifact_saving_to_provider():
    captured = []

    def model(messages, info):
        captured.append(info.instructions)
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {
            "action": "answer", "text": "Supplier B meets the requested deadline.",
        })])

    runner = make_runner(action="answer", text="unused")
    runner.agent = Agent(FunctionModel(model), output_type=ConversationStep,
                         instructions=conversation_agent.INSTRUCTIONS)
    await runner.run(ConversationAgentInput(mode="task", instruction="Delegate a comparison report"))
    assert "EXECUTE AN ALREADY DELEGATED TASK" in captured[0]
    assert "automatically saves task answers" in captured[0]
    assert "Never list cases as a prerequisite" in captured[0]


async def test_already_supplied_case_list_cannot_be_requested_again():
    task = ConversationAgentInput(
        mode="task", instruction="Explain our queue",
        observations=[ToolObservation(tool="list_cases", content="[]")],
    )
    with pytest.raises(ValueError, match="repeated lookup"):
        await make_runner(action="tool", tool="list_cases", text="Read cases again").run(task)


async def test_repeated_case_read_is_blocked_even_when_case_was_not_found():
    task = ConversationAgentInput(mode="task", instruction="Read case_missing",
        observations=[ToolObservation(tool="read_case", case_id="case_missing", content="Case not found.")])
    with pytest.raises(ValueError, match="repeated lookup"):
        await make_runner(action="tool", tool="read_case", case_id="case_missing", text="Retry").run(task)


async def test_review_has_no_tools_and_cannot_be_supplied_by_task_writer():
    task = ConversationAgentInput(mode="review", instruction="Review the draft",
                                  candidate="A draft", acceptance_criteria=["Write a draft"])
    with pytest.raises(ValueError, match="completion review"):
        await make_runner(action="tool", tool="list_cases", text="Read cases").run(task)
    with pytest.raises(ValueError, match="independent review"):
        await make_runner(action="answer", text="A draft", review={}).run(
            ConversationAgentInput(mode="task", instruction="Write a draft")
        )


async def test_fixture_review_only_passes_explicit_simulation_criterion():
    runner = ConversationFixtureRunner()
    sources = [WorkSource(id="src_terms", title="Terms", content="Payment within 30 days.")]
    candidate = await runner.run(ConversationAgentInput(mode="task", instruction="Prepare report", sources=sources))
    criteria = [conversation_agent.FIXTURE_CRITERION]
    result = await runner.run(ConversationAgentInput(mode="review", instruction="Review", sources=sources,
                                                    candidate=candidate.step.text, acceptance_criteria=criteria))
    assert validate_completion(candidate.step.text, criteria, sources, result.step.review)["passed"]
    result = await runner.run(ConversationAgentInput(mode="review", instruction="Review", sources=sources,
                                                    candidate=candidate.step.text, acceptance_criteria=["Recommend the best supplier"]))
    assert not result.step.review.criteria[0].passed


def test_run_identifier_never_reaches_model_prompt():
    task = ConversationAgentInput(mode="chat", instruction="Hello", run_id="private_runtime_id")
    assert "private_runtime_id" not in conversation_agent.prompt_for(task)


async def test_fixture_is_labelled_and_supports_delegation_missing_input_and_case_reads():
    runner = ConversationFixtureRunner()
    response = await runner.run(ConversationAgentInput(mode="chat", instruction="Hello"))
    assert response.model.startswith("fixture:")
    assert "offline fixture" in response.step.text
    response = await runner.run(ConversationAgentInput(mode="chat", instruction="Prepare a report"))
    assert response.step.action == "delegate"
    response = await runner.run(ConversationAgentInput(mode="task", instruction="Prepare a report"))
    assert response.step.action == "need_input"
    response = await runner.run(
        ConversationAgentInput(mode="task", instruction="Investigate case_example")
    )
    assert response.step.tool == "read_case"
    assert response.step.case_id == "case_example"
    response = await runner.run(
        ConversationAgentInput(mode="chat", instruction="Prepare " + "x" * 4000)
    )
    assert response.step.action == "need_input"


async def test_fixture_report_does_not_claim_model_authorship():
    response = await ConversationFixtureRunner().run(ConversationAgentInput(
        mode="task", instruction="Prepare a report",
        sources=[WorkSource(id="src_terms", title="Terms", content="Payment within 30 days.")],
    ))
    assert response.step.action == "answer"
    assert "not model-authored" in response.step.text
    assert "Payment within 30 days" in response.step.text
    assert response.step.citations == ["src_terms"]


def test_conversation_endpoint_requires_private_worker_token(monkeypatch):
    monkeypatch.setattr(agents, "settings", replace(agents.settings, agent_token="test-token"))
    monkeypatch.setattr(agents, "make_runner", lambda: agents.FixtureRunner())
    monkeypatch.setattr(agents, "make_conversation_runner", ConversationFixtureRunner)
    with TestClient(agents.create_agent_app()) as client:
        request = {"mode": "chat", "instruction": "Hello"}
        assert client.post("/conversation/run", json=request).status_code == 401
        response = client.post("/conversation/run", json=request,
                               headers={"Authorization": "Bearer test-token"})
        assert response.status_code == 200
        assert response.json()["model"] == "fixture:conversation-v1"
        assert client.post("/conversation/run", json={**request, "max_steps": 100},
                           headers={"Authorization": "Bearer test-token"}).status_code == 422


async def test_claude_cli_has_no_tools_keys_hooks_or_persistent_session(monkeypatch):
    monkeypatch.setenv("FEYA_GATEWAY_TOKEN", "must-not-leak")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "must-not-be-billed")
    monkeypatch.setattr(conversation_agent.shutil, "which", lambda _: "/test/claude")
    calls = []

    class Process:
        returncode = 0

        async def communicate(self, prompt):
            assert json.loads(prompt)["instruction"] == "Hello"
            return json.dumps({
                "structured_output": {"action": "answer", "text": "Hello"},
                "usage": {"input_tokens": 100, "output_tokens": 10},
            }).encode(), b""

    async def subprocess(*args, **kwargs):
        calls.append((args, kwargs))
        return Process()

    monkeypatch.setattr(conversation_agent.asyncio, "create_subprocess_exec", subprocess)
    result = await ConversationClaudeRunner().run(
        ConversationAgentInput(mode="chat", instruction="Hello")
    )
    args, options = calls[0]
    assert args[args.index("--tools") + 1] == ""
    assert args[args.index("--mcp-config") + 1] == '{"mcpServers":{}}'
    assert args[args.index("--settings") + 1] == '{"disableAllHooks":true}'
    assert "--no-session-persistence" in args
    assert "FEYA_GATEWAY_TOKEN" not in options["env"]
    assert "ANTHROPIC_API_KEY" not in options["env"]
    assert result.step.text == "Hello"


async def test_claude_cli_is_killed_when_request_is_cancelled(monkeypatch):
    monkeypatch.setattr(conversation_agent.shutil, "which", lambda _: "/test/claude")

    class Process:
        returncode = None
        killed = False
        waited = False

        async def communicate(self, _):
            raise asyncio.CancelledError()

        def kill(self):
            self.killed = True

        async def wait(self):
            self.waited = True

    process = Process()

    async def subprocess(*args, **kwargs):
        return process

    monkeypatch.setattr(conversation_agent.asyncio, "create_subprocess_exec", subprocess)
    with pytest.raises(asyncio.CancelledError):
        await ConversationClaudeRunner().run(
            ConversationAgentInput(mode="chat", instruction="Hello")
        )
    assert process.killed and process.waited


@pytest.mark.parametrize(("returncode", "payload", "expected"), [
    (1, {"error": "not logged in: sensitive details"}, "auth_expired"),
    (0, {"is_error": True, "error": "rate limit: sensitive details"}, "rate_limited"),
    (0, {"unexpected": "sensitive details"}, "invalid_output"),
])
async def test_claude_failures_have_safe_categories(monkeypatch, returncode, payload, expected):
    from feya.reasoning_errors import ReasoningFailure

    monkeypatch.setattr(conversation_agent.shutil, "which", lambda _: "/test/claude")

    class Process:
        async def communicate(self, _):
            return json.dumps(payload).encode(), b""

    process = Process()
    process.returncode = returncode

    async def subprocess(*args, **kwargs):
        return process

    monkeypatch.setattr(conversation_agent.asyncio, "create_subprocess_exec", subprocess)
    with pytest.raises(ReasoningFailure) as failure:
        await ConversationClaudeRunner().run(ConversationAgentInput(mode="chat", instruction="Hello"))
    assert failure.value.code == expected
    assert "sensitive details" not in str(failure.value)


async def test_review_treats_delegation_as_already_fulfilled():
    captured = []

    def model(messages, info):
        captured.append(info.instructions)
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {
            "action": "answer", "text": "The requested comparison is present.",
            "review": {"criteria": [{"criterion_index": 0, "passed": True, "reason": "Comparison supplied"}]},
        })])

    runner = make_runner(action="answer", text="unused")
    runner.agent = Agent(FunctionModel(model), output_type=ConversationStep,
                         instructions=conversation_agent.INSTRUCTIONS)
    await runner.run(ConversationAgentInput(
        mode="review", instruction="Compare the suppliers. Delegate this as a task.",
        acceptance_criteria=["Compare the suppliers"], candidate="A is cheaper; B arrives earlier.",
    ))
    assert "application has fulfilled requests to delegate" in captured[0]
    assert "Still assess all requested artifact content" in captured[0]
