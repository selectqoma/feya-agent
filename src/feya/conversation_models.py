"""Bounded contracts shared by conversation clients, workers and reasoning."""

from typing import Literal

from pydantic import Field, model_validator

from feya.domain import Contract, Identifier


class ConversationCreate(Contract):
    title: str = Field(default="New conversation", min_length=1, max_length=160)


class ConversationMessage(Contract):
    content: str = Field(min_length=1, max_length=8000)
    request_id: Identifier


class SourceCreate(Contract):
    title: str = Field(min_length=1, max_length=160)
    content: str = Field(min_length=1, max_length=12000)


class TaskCommand(Contract):
    expected_version: int = Field(ge=1)
    instruction: str = Field(default="", max_length=4000)


class ChatMessage(Contract):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=12000)


class WorkSource(Contract):
    id: Identifier
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=16000)


class ToolObservation(Contract):
    tool: Literal["list_cases", "read_case"]
    content: str = Field(min_length=1, max_length=16000)


class ConversationAgentInput(Contract):
    mode: Literal["chat", "task"]
    instruction: str = Field(min_length=1, max_length=8000)
    history: list[ChatMessage] = Field(default_factory=list, max_length=20)
    sources: list[WorkSource] = Field(default_factory=list, max_length=12)
    observations: list[ToolObservation] = Field(default_factory=list, max_length=6)
    max_steps: int = Field(default=4, ge=1, le=6)
    max_input_tokens: int = Field(default=16000, ge=1, le=32000)
    max_output_tokens: int = Field(default=3000, ge=1, le=6000)
    deadline_seconds: int = Field(default=90, ge=1, le=180)


class ConversationStep(Contract):
    action: Literal["answer", "delegate", "need_input", "tool"]
    text: str = Field(min_length=1, max_length=12000)
    objective: str = Field(default="", max_length=4000)
    deliverable: str = Field(default="", max_length=1000)
    tool: Literal["list_cases", "read_case"] | None = None
    case_id: Identifier | None = None
    citations: list[Identifier] = Field(default_factory=list, max_length=12)

    @model_validator(mode="after")
    def valid_action(self):
        if self.action == "delegate" and (not self.objective.strip() or not self.deliverable.strip()):
            raise ValueError("Delegation requires an objective and a deliverable")
        if self.action == "tool":
            if self.tool is None or (self.tool == "read_case" and self.case_id is None):
                raise ValueError("A tool request must specify its required arguments")
        elif self.tool is not None or self.case_id is not None:
            raise ValueError("Only tool requests may contain tool arguments")
        return self


class ConversationAgentResult(Contract):
    step: ConversationStep
    model: str
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
