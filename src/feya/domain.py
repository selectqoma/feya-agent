import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


def now() -> datetime:
    return datetime.now(UTC)


def uid(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


def digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        ).encode()
    ).hexdigest()


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Phase(StrEnum):
    NEW = "new"
    TRIAGED = "triaged"
    WAITING = "waiting_for_information"
    READY = "ready"
    DRAFTING = "drafting"
    DRAFTED = "drafted"
    REVIEW = "awaiting_review"
    EXECUTE = "ready_to_execute"
    EXECUTING = "executing"
    VERIFY = "verify_pending"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"
    RECONCILE = "reconciliation_required"


# Business state changes always go through this map, including human overrides.
TRANSITIONS = {
    "source.recorded": (
        set(Phase) - {Phase.CANCELLED, Phase.EXECUTING, Phase.VERIFY, Phase.RECONCILE},
        Phase.NEW,
    ),
    "triage.completed": ({Phase.NEW, Phase.BLOCKED}, Phase.TRIAGED),
    "information.missing": ({Phase.TRIAGED}, Phase.WAITING),
    "information.sufficient": ({Phase.TRIAGED}, Phase.READY),
    "draft.created": ({Phase.READY}, Phase.DRAFTED),
    "approval.requested": ({Phase.DRAFTED}, Phase.REVIEW),
    "approval.granted": ({Phase.REVIEW}, Phase.EXECUTE),
    "action.started": ({Phase.EXECUTE, Phase.WAITING}, Phase.EXECUTING),
    "action.returned": ({Phase.EXECUTING, Phase.RECONCILE}, Phase.VERIFY),
    "draft.verified": ({Phase.VERIFY}, Phase.WAITING),
    "case.completed": ({Phase.VERIFY}, Phase.COMPLETED),
    "action.uncertain": ({Phase.EXECUTING, Phase.VERIFY, Phase.RECONCILE}, Phase.RECONCILE),
    "case.blocked": (
        set(Phase) - {Phase.COMPLETED, Phase.CANCELLED, Phase.RECONCILE},
        Phase.BLOCKED,
    ),
    "case.cancelled": (
        set(Phase) - {Phase.EXECUTING, Phase.VERIFY, Phase.RECONCILE, Phase.COMPLETED},
        Phase.CANCELLED,
    ),
    "case.manual_completed": (
        set(Phase) - {Phase.EXECUTING, Phase.VERIFY, Phase.RECONCILE, Phase.CANCELLED},
        Phase.COMPLETED,
    ),
}


def transition(phase: str, event: str, *, verified: bool = False, reason: str = "") -> str:
    allowed, target = TRANSITIONS[event]
    if phase not in allowed:
        raise ValueError(f"Cannot apply {event} while case is {phase}")
    if event in {"case.completed", "draft.verified"} and not verified:
        raise ValueError("Provider read-back is required")
    if event == "case.manual_completed" and not reason.strip():
        raise ValueError("Manual completion requires a reason")
    return target.value


Identifier = Annotated[str, Field(min_length=1, max_length=160, pattern=r"^[a-zA-Z0-9_.:-]+$")]


class Inbound(Contract):
    event_id: Identifier
    thread_id: Identifier
    pack_id: Identifier
    sender: str = Field(min_length=3, max_length=254, pattern=r"^[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+$")
    subject: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=16000)

    @field_validator("sender", "subject")
    @classmethod
    def no_header_injection(cls, value: str) -> str:
        if "\r" in value or "\n" in value:
            raise ValueError("Header contains a newline")
        return value


class Claim(Contract):
    key: str = Field(max_length=80)
    value: str = Field(min_length=1, max_length=1000)
    evidence_id: str
    quote: str = Field(min_length=1, max_length=1000)


class Triage(Contract):
    summary: str = Field(min_length=1, max_length=600)
    claims: list[Claim] = Field(max_length=24)
    warnings: list[str] = Field(default_factory=list, max_length=10)


class AgentTask(Contract):
    tenant_id: str
    case_id: str
    role: Literal["triage", "status"] = "triage"
    prompt_version: Literal["triage:1"] = "triage:1"
    required_fields: list[str]
    evidence: list[dict] = Field(max_length=30)
    max_steps: int = Field(default=2, ge=1, le=4)
    max_input_tokens: int = Field(default=12000, ge=1, le=16000)
    max_output_tokens: int = Field(default=2000, ge=1, le=4000)
    deadline_seconds: int = Field(default=90, ge=1, le=180)


class AgentResult(Contract):
    output: Triage
    model: str
    input_tokens: int | None = None
    output_tokens: int | None = None


Money = Annotated[str, Field(pattern=r"^(0|[1-9][0-9]{0,7})\.[0-9]{2}$")]


class EmailDraft(Contract):
    to: str = Field(max_length=254)
    subject: str = Field(max_length=200)
    body: str = Field(min_length=1, max_length=8000)


class OfferDraft(Contract):
    customer_email: str
    service: str
    quantity: str = Field(pattern=r"^[1-9][0-9]{0,2}$")
    unit_price: Money
    subtotal: Money
    tax: Money
    total: Money
    currency: Literal["EUR", "USD", "GBP"]
    rate_version: str
    status: Literal["draft"] = "draft"


class Proposal(Contract):
    capability: Literal["email.draft.create", "accounting.offer.create_draft"]
    payload: dict
    evidence_ids: list[str] = Field(min_length=1, max_length=30)


class Decision(Contract):
    decision: Literal["approve", "reject"]
    expected_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    reason: str = Field(min_length=1, max_length=500)


class CaseCommand(Contract):
    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=500)


class Fault(Contract):
    mode: Literal["none", "timeout_before", "timeout_after", "mismatch", "read_failure"]


def decimal_money(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.01")), ".2f")
