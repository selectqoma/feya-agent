"""Initial local prototype schema; freeze before the first distributed release."""

from alembic import op
from feya.db import metadata

revision = "0001"
down_revision = None


def upgrade():
    # shortcut: initial migration uses live metadata, freeze explicit DDL before distributing releases.
    metadata.create_all(op.get_bind())
    op.execute("""CREATE FUNCTION prevent_audit_change() RETURNS trigger LANGUAGE plpgsql AS $$
      BEGIN RAISE EXCEPTION 'Audit events are append-only'; END; $$""")
    op.execute("""CREATE TRIGGER immutable_audit BEFORE UPDATE OR DELETE ON audit_events
      FOR EACH ROW EXECUTE FUNCTION prevent_audit_change()""")


def downgrade():
    raise RuntimeError("Destructive downgrade disabled; restore an explicit backup")
