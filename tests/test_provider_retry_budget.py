import httpx
import httpx2
import pytest
from anthropic import AsyncAnthropic
from openai import AsyncOpenAI
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.models.openai_codex import OpenAICodexModel
from pydantic_ai.providers.anthropic import AnthropicProvider
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.providers.openai_codex import OpenAICodexProvider

from feya import conversation_agent
from feya.conversation_models import ConversationAgentInput
from feya.reasoning_errors import classify_failure


@pytest.mark.parametrize("provider", ["openai", "anthropic", "openai-codex"])
@pytest.mark.parametrize("failure", [429, 503, "timeout", "connection"])
async def test_one_reserved_run_makes_one_sdk_attempt(monkeypatch, provider, failure):
    attempts = []
    transport = httpx2 if provider == "anthropic" else httpx

    def respond(request):
        attempts.append(request)
        if failure == "connection":
            raise transport.ConnectError("Synthetic connection failure", request=request)
        if failure == "timeout":
            raise transport.ReadTimeout("Synthetic timeout", request=request)
        return transport.Response(failure, json={"error": {"message": "Synthetic failure", "type": "test"}})

    async with transport.AsyncClient(transport=transport.MockTransport(respond)) as http:
        if provider == "anthropic":
            client = AsyncAnthropic(api_key="synthetic", http_client=http)
            model = AnthropicModel("claude-sonnet-4-6", provider=AnthropicProvider(anthropic_client=client))
        else:
            client = AsyncOpenAI(api_key="synthetic", http_client=http)
            model = (
                OpenAICodexModel("gpt-5", provider=OpenAICodexProvider(openai_client=client))
                if provider == "openai-codex" else
                OpenAIChatModel("gpt-4o-mini", provider=OpenAIProvider(openai_client=client))
            )
        assert client.max_retries == 2
        monkeypatch.setattr(conversation_agent, "infer_model", lambda _: model)
        runner = conversation_agent.ConversationPydanticRunner(f"{provider}:test")
        assert client.max_retries == 0
        with pytest.raises(Exception) as raised:
            await runner.run(ConversationAgentInput(mode="chat", instruction="Hello", max_steps=1))
        assert len(attempts) == 1
        expected = "rate_limited" if failure == 429 else "timeout" if failure == "timeout" else "unavailable"
        assert classify_failure(raised.value).code == expected, (type(raised.value), repr(raised.value), repr(raised.value.__cause__))
