from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    ForeignKeyConstraint,
    Integer,
    MetaData,
    String,
    Table,
    UniqueConstraint,
    create_engine,
)

from feya.domain import now

metadata = MetaData()


def scoped(name, *columns, case_link=False, constraints=()):
    fields: list = [
        Column("tenant_id", String, primary_key=True),
        Column("id", String, primary_key=True),
    ]
    if case_link:
        fields += [
            Column("case_id", String, nullable=False),
            ForeignKeyConstraint(["tenant_id", "case_id"], ["cases.tenant_id", "cases.id"]),
        ]
    return Table(
        name,
        metadata,
        *fields,
        *columns,
        Column("created_at", DateTime(timezone=True), default=now, nullable=False),
        *constraints,
    )


cases = scoped(
    "cases",
    Column("thread_id", String, nullable=False),
    Column("pack_id", String, nullable=False),
    Column("pack_hash", String, nullable=False),
    Column("customer_email", String, nullable=False),
    Column("subject", String, nullable=False),
    Column("phase", String, nullable=False),
    Column("version", Integer, nullable=False, default=1),
    Column("source_revision", Integer, nullable=False, default=0),
    Column("summary", String, default="", nullable=False),
    Column("facts", JSON, default=dict, nullable=False),
    Column("missing", JSON, default=list, nullable=False),
    Column("next_action", String, default="Analyse the enquiry", nullable=False),
    Column("completion_kind", String),
    constraints=[UniqueConstraint("tenant_id", "thread_id")],
)

evidence = scoped(
    "evidence",
    Column("event_id", String, nullable=False),
    Column("provider", String, default="fake_email", nullable=False),
    Column("external_object_id", String, nullable=False),
    Column("source_uri", String, nullable=False),
    Column("content", JSON, nullable=False),
    Column("content_hash", String, nullable=False),
    Column("revision", Integer, nullable=False),
    case_link=True,
    constraints=[UniqueConstraint("tenant_id", "provider", "event_id")],
)

audit = scoped(
    "audit_events",
    Column("kind", String, nullable=False),
    Column("actor", String, nullable=False),
    Column("case_version", Integer, nullable=False),
    Column("detail", JSON, nullable=False),
    case_link=True,
)

outbox = scoped(
    "outbox_events",
    Column("kind", String, nullable=False),
    Column("payload", JSON, nullable=False),
    Column("published", Boolean, default=False, nullable=False),
    Column("processed", Boolean, default=False, nullable=False),
    case_link=True,
)

runs = scoped(
    "agent_runs",
    Column("role", String, nullable=False),
    Column("model", String, nullable=False),
    Column("prompt_version", String, nullable=False),
    Column("pack_hash", String, nullable=False),
    Column("source_revision", Integer, nullable=False),
    Column("status", String, nullable=False),
    Column("usage", JSON, nullable=False),
    Column("evidence_ids", JSON, nullable=False),
    case_link=True,
)

artifacts = scoped(
    "artifacts",
    Column("kind", String, nullable=False),
    Column("content", JSON, nullable=False),
    Column("content_hash", String, nullable=False),
    Column("source_revision", Integer, nullable=False),
    case_link=True,
)

intents = scoped(
    "action_intents",
    Column("capability", String, nullable=False),
    Column("payload", JSON, nullable=False),
    Column("evidence_ids", JSON, nullable=False),
    Column("source_revision", Integer, nullable=False),
    Column("pack_hash", String, nullable=False),
    Column("digest", String, nullable=False),
    Column("status", String, nullable=False),
    Column("policy_effect", String, nullable=False),
    Column("policy_reasons", JSON, nullable=False),
    Column("provider_ref", String),
    Column("idempotency_key", String, nullable=False),
    case_link=True,
    constraints=[UniqueConstraint("tenant_id", "idempotency_key")],
)

approvals = scoped(
    "approvals",
    Column("intent_id", String, nullable=False),
    Column("digest", String, nullable=False),
    Column("actor", String, nullable=False),
    Column("decision", String, nullable=False),
    Column("reason", String, nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Column("consumed_at", DateTime(timezone=True)),
    Column("revoked_at", DateTime(timezone=True)),
    case_link=True,
    constraints=[
        UniqueConstraint("tenant_id", "intent_id"),
        ForeignKeyConstraint(
            ["tenant_id", "intent_id"], ["action_intents.tenant_id", "action_intents.id"]
        ),
    ],
)

attempts = scoped(
    "execution_attempts",
    Column("intent_id", String, nullable=False),
    Column("status", String, nullable=False),
    Column("error", String),
    case_link=True,
    constraints=[
        UniqueConstraint("tenant_id", "intent_id"),
        ForeignKeyConstraint(
            ["tenant_id", "intent_id"], ["action_intents.tenant_id", "action_intents.id"]
        ),
    ],
)

verifications = scoped(
    "verifications",
    Column("intent_id", String, nullable=False),
    Column("provider_ref", String, nullable=False),
    Column("passed", Boolean, nullable=False),
    Column("expected_hash", String, nullable=False),
    Column("observed_hash", String, nullable=False),
    Column("checked_fields", JSON, nullable=False),
    case_link=True,
    constraints=[
        ForeignKeyConstraint(
            ["tenant_id", "intent_id"], ["action_intents.tenant_id", "action_intents.id"]
        )
    ],
)

# The simulated provider has its own committed state, independently read back by the gateway.
provider_objects = scoped(
    "fake_provider_objects",
    Column("operation_key", String, nullable=False),
    Column("capability", String, nullable=False),
    Column("payload", JSON, nullable=False),
    constraints=[UniqueConstraint("tenant_id", "operation_key")],
)
provider_faults = scoped("fake_provider_faults", Column("mode", String, nullable=False))


def make_engine(url: str):
    if not url.startswith("postgresql"):
        raise ValueError("Feya requires PostgreSQL; no alternate durability engine")
    return create_engine(url, pool_pre_ping=True, pool_size=5, max_overflow=5)


def scope(table, tenant: str, object_id: str | None = None):
    clause = table.c.tenant_id == tenant
    return clause if object_id is None else clause & (table.c.id == object_id)


def json_row(row) -> dict:
    result = dict(row)
    return {k: v.isoformat() if hasattr(v, "isoformat") else v for k, v in result.items()}
