import pytest
from pydantic_ai import Agent
from pydantic_ai.models.test import TestModel

from feya.agents import PydanticAIRunner
from feya.domain import AgentTask, Triage


def make_test_runner():
    runner = object.__new__(PydanticAIRunner)
    runner.model = "test:structured"
    runner.agent = Agent(
        TestModel(
            custom_output_args={"summary": "Synthetic request", "claims": [], "warnings": []}
        ),
        output_type=Triage,
    )
    return runner


async def test_pydantic_structured_result_and_usage():
    task = AgentTask(
        tenant_id="test",
        case_id="case_test",
        required_fields=["quantity"],
        evidence=[{"id": "src_1", "body": "quantity: 2"}],
    )
    result = await make_test_runner().run(task)
    assert result.output.summary == "Synthetic request"
    assert result.input_tokens > 0
    assert result.output_tokens > 0


async def test_input_budget_blocks_before_model():
    task = AgentTask(
        tenant_id="test",
        case_id="case_test",
        required_fields=["quantity"],
        evidence=[{"id": "src_1", "body": "quantity: 2"}],
        max_input_tokens=1,
    )
    with pytest.raises(ValueError, match="budget"):
        await make_test_runner().run(task)
