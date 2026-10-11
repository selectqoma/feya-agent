"""Safe, stable failure categories; provider messages never cross this boundary."""

import httpx
from anthropic import APIConnectionError as AnthropicConnectionError
from anthropic import APITimeoutError as AnthropicTimeoutError
from openai import APIConnectionError as OpenAIConnectionError
from openai import APITimeoutError as OpenAITimeoutError
from pydantic import ValidationError
from pydantic_ai.exceptions import (
    ModelAPIError,
    ModelHTTPError,
    UnexpectedModelBehavior,
    UsageLimitExceeded,
)

FAILURES = {
    "auth_expired": (False, "Sign in to the configured model account again, then resume."),
    "rate_limited": (True, "The model account is rate limited. Automatic retries require remaining work budget."),
    "timeout": (True, "The model request timed out. Automatic retries require remaining work budget."),
    "unavailable": (True, "The reasoning service is temporarily unavailable. Automatic retries require remaining work budget."),
    "invalid_output": (False, "The model returned an invalid result. Review the task instructions and resume."),
    "context_limit": (False, "The material exceeds the context limit. Start a conversation with shorter source excerpts, or narrow the request."),
    "budget_exhausted": (False, "This run exhausted its budget. Resume if task budget remains; otherwise start a narrower task."),
    "cancelled": (False, "The reasoning request was cancelled. Any provider usage already incurred may still count."),
    "internal_error": (False, "An internal error stopped this task. Check the local service and retry after the issue is resolved."),
}


class ReasoningFailure(Exception):
    def __init__(self, code: str):
        self.code = code if code in FAILURES else "internal_error"
        self.retryable, self.message = FAILURES[self.code]
        super().__init__(self.message)

    def as_dict(self):
        return {"code": self.code, "message": self.message, "retryable": self.retryable}


def classify_failure(exc: Exception) -> ReasoningFailure:
    if isinstance(exc, ReasoningFailure):
        return exc
    if isinstance(exc, ModelAPIError) and isinstance(exc.__cause__, (OpenAIConnectionError, AnthropicConnectionError)):
        return classify_failure(exc.__cause__)
    if isinstance(exc, (TimeoutError, httpx.TimeoutException, OpenAITimeoutError, AnthropicTimeoutError)):
        return ReasoningFailure("timeout")
    if isinstance(exc, UsageLimitExceeded):
        return ReasoningFailure("budget_exhausted")
    if isinstance(exc, (ModelHTTPError, httpx.HTTPStatusError)):
        status = exc.status_code if isinstance(exc, ModelHTTPError) else exc.response.status_code
        code = (
            "auth_expired" if status in {401, 403}
            else "rate_limited" if status == 429
            else "timeout" if status in {408, 504}
            else "unavailable" if status >= 500
            else "invalid_output"
        )
        return ReasoningFailure(code)
    if isinstance(exc, (httpx.RequestError, OpenAIConnectionError, AnthropicConnectionError)):
        return ReasoningFailure("unavailable")
    if isinstance(exc, (ValidationError, UnexpectedModelBehavior, ValueError)):
        return ReasoningFailure("invalid_output")
    return ReasoningFailure("internal_error")
