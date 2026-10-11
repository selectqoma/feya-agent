"""Preserve task results, enforce review and carry budgets across task generations."""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"


def upgrade():
    for name in ("candidate_markdown", "failure_message"):
        op.add_column("delegated_tasks", sa.Column(name, sa.String(), nullable=False, server_default=""))
    for name, default in (("acceptance_criteria", "[]"), ("completion_checks", "{}")):
        op.add_column("delegated_tasks", sa.Column(name, sa.JSON(), nullable=False, server_default=default))
    for name in ("completion_label", "error_code"):
        op.add_column("delegated_tasks", sa.Column(name, sa.String()))
    for name in ("calls_reserved", "tokens_reserved", "seconds_reserved", "unknown_usage_calls"):
        op.add_column("delegated_tasks", sa.Column(name, sa.Integer(), nullable=False, server_default="0"))
    op.add_column("work_events", sa.Column("stage", sa.String(), nullable=False, server_default="draft"))
    op.add_column("work_events", sa.Column("candidate", sa.String()))
    op.add_column("work_events", sa.Column("next_attempt_at", sa.DateTime(timezone=True)))
    op.add_column("work_events", sa.Column("failure_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("work_events", sa.Column("error_code", sa.String()))
    # Existing attempts consumed real capacity, even when their usage response was lost.
    op.execute("""UPDATE delegated_tasks AS task SET
        calls_reserved = spent.calls, unknown_usage_calls = spent.calls,
        tokens_reserved = spent.calls * 35000, seconds_reserved = spent.calls * 90
        FROM (SELECT tenant_id, task_id, SUM(attempts)::integer AS calls FROM work_events
              WHERE task_id IS NOT NULL GROUP BY tenant_id, task_id) AS spent
        WHERE task.tenant_id = spent.tenant_id AND task.id = spent.task_id""")
    op.execute("""UPDATE delegated_tasks SET
        acceptance_criteria = json_build_array(CASE WHEN char_length(deliverable) <= 500
            THEN deliverable ELSE 'Produce the deliverable described in the task brief.' END),
        candidate_markdown = result_markdown,
        completion_label = CASE WHEN status = 'completed' THEN 'legacy_unreviewed' ELSE NULL END""")


def downgrade():
    raise RuntimeError("Destructive downgrade disabled; restore an explicit backup")
