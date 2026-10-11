"""Conversation tables are separate from the frozen case bootstrap migration."""

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
)

from feya.domain import now

metadata = MetaData()


def scoped(name, *columns, constraints=()):
    return Table(
        name,
        metadata,
        Column("tenant_id", String, primary_key=True),
        Column("id", String, primary_key=True),
        *columns,
        Column("created_at", DateTime(timezone=True), default=now, nullable=False),
        *constraints,
    )


def conversation_link():
    return ForeignKeyConstraint(
        ["tenant_id", "conversation_id"], ["conversations.tenant_id", "conversations.id"]
    )


conversations = scoped(
    "conversations",
    Column("title", String, nullable=False),
    Column("sequence", Integer, nullable=False, default=0),
)
messages = scoped(
    "conversation_messages",
    Column("conversation_id", String, nullable=False),
    Column("sequence", Integer, nullable=False),
    Column("role", String, nullable=False),
    Column("content", String, nullable=False),
    Column("request_id", String),
    Column("reply_to", String),
    Column("task_id", String),
    constraints=[
        conversation_link(),
        ForeignKeyConstraint(
            ["tenant_id", "task_id"], ["delegated_tasks.tenant_id", "delegated_tasks.id"], name="fk_message_task"
        ),
        ForeignKeyConstraint(
            ["tenant_id", "reply_to"], ["conversation_messages.tenant_id", "conversation_messages.id"], name="fk_message_reply"
        ),
        UniqueConstraint("tenant_id", "conversation_id", "sequence"),
        UniqueConstraint("tenant_id", "conversation_id", "request_id"),
    ],
)
sources = scoped(
    "conversation_sources",
    Column("conversation_id", String, nullable=False),
    Column("title", String, nullable=False),
    Column("content", String, nullable=False),
    constraints=[conversation_link()],
)
tasks = scoped(
    "delegated_tasks",
    Column("conversation_id", String, nullable=False),
    Column("objective", String, nullable=False),
    Column("deliverable", String, nullable=False),
    Column("instruction", String, nullable=False),
    Column("status", String, nullable=False),
    Column("version", Integer, default=1, nullable=False),
    Column("generation", Integer, default=1, nullable=False),
    Column("result_markdown", String, default="", nullable=False),
    Column("candidate_markdown", String, default="", nullable=False),
    Column("acceptance_criteria", JSON, default=list, nullable=False),
    Column("completion_checks", JSON, default=dict, nullable=False),
    Column("completion_label", String),
    Column("error_code", String),
    Column("failure_message", String, default="", nullable=False),
    Column("calls_reserved", Integer, default=0, nullable=False),
    Column("tokens_reserved", Integer, default=0, nullable=False),
    Column("seconds_reserved", Integer, default=0, nullable=False),
    Column("unknown_usage_calls", Integer, default=0, nullable=False),
    Column("sources", JSON, nullable=False),
    Column("history", JSON, nullable=False),
    constraints=[conversation_link()],
)
events = scoped(
    "work_events",
    Column("conversation_id", String, nullable=False),
    Column("task_id", String),
    Column("message_id", String),
    Column("sequence", Integer, nullable=False),
    Column("kind", String, nullable=False),
    Column("generation", Integer, nullable=False, default=1),
    Column("instruction", String, nullable=False),
    Column("attempts", Integer, nullable=False, default=0),
    Column("stage", String, nullable=False, default="draft"),
    Column("candidate", String),
    Column("next_attempt_at", DateTime(timezone=True)),
    Column("failure_count", Integer, default=0, nullable=False),
    Column("error_code", String),
    Column("sources", JSON, nullable=False),
    Column("history", JSON, nullable=False),
    Column("observations", JSON, nullable=False, default=list),
    Column("usage", JSON, nullable=False, default=list),
    Column("lease_token", String),
    Column("lease_until", DateTime(timezone=True)),
    Column("published", Boolean, default=False, nullable=False),
    Column("processed", Boolean, default=False, nullable=False),
    constraints=[
        conversation_link(),
        ForeignKeyConstraint(
            ["tenant_id", "task_id"], ["delegated_tasks.tenant_id", "delegated_tasks.id"]
        ),
        ForeignKeyConstraint(
            ["tenant_id", "message_id"],
            ["conversation_messages.tenant_id", "conversation_messages.id"],
        ),
    ],
)
progress = scoped(
    "task_progress",
    Column("task_id", String, nullable=False),
    Column("kind", String, nullable=False),
    Column("content", String, nullable=False),
    Column("generation", Integer, nullable=False),
    constraints=[
        ForeignKeyConstraint(
            ["tenant_id", "task_id"], ["delegated_tasks.tenant_id", "delegated_tasks.id"]
        )
    ],
)
