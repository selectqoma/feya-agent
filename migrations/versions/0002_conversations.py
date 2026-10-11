"""Durable conversations and bounded delegated tasks."""

from alembic import op

revision = "0002"
down_revision = "0001"


def upgrade():
    op.execute('CREATE TABLE conversations (\n\ttenant_id VARCHAR NOT NULL, \n\tid VARCHAR NOT NULL, \n\ttitle VARCHAR NOT NULL, \n\tsequence INTEGER NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (tenant_id, id)\n)')
    op.execute('CREATE TABLE conversation_sources (\n\ttenant_id VARCHAR NOT NULL, \n\tid VARCHAR NOT NULL, \n\tconversation_id VARCHAR NOT NULL, \n\ttitle VARCHAR NOT NULL, \n\tcontent VARCHAR NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (tenant_id, id), \n\tFOREIGN KEY(tenant_id, conversation_id) REFERENCES conversations (tenant_id, id)\n)')
    op.execute('CREATE TABLE delegated_tasks (\n\ttenant_id VARCHAR NOT NULL, \n\tid VARCHAR NOT NULL, \n\tconversation_id VARCHAR NOT NULL, \n\tobjective VARCHAR NOT NULL, \n\tdeliverable VARCHAR NOT NULL, \n\tinstruction VARCHAR NOT NULL, \n\tstatus VARCHAR NOT NULL, \n\tversion INTEGER NOT NULL, \n\tgeneration INTEGER NOT NULL, \n\tresult_markdown VARCHAR NOT NULL, \n\tsources JSON NOT NULL, \n\thistory JSON NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (tenant_id, id), \n\tFOREIGN KEY(tenant_id, conversation_id) REFERENCES conversations (tenant_id, id)\n)')
    op.execute('CREATE TABLE conversation_messages (\n\ttenant_id VARCHAR NOT NULL, \n\tid VARCHAR NOT NULL, \n\tconversation_id VARCHAR NOT NULL, \n\tsequence INTEGER NOT NULL, \n\trole VARCHAR NOT NULL, \n\tcontent VARCHAR NOT NULL, \n\trequest_id VARCHAR, \n\treply_to VARCHAR, \n\ttask_id VARCHAR, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (tenant_id, id), \n\tFOREIGN KEY(tenant_id, conversation_id) REFERENCES conversations (tenant_id, id), \n\tCONSTRAINT fk_message_task FOREIGN KEY(tenant_id, task_id) REFERENCES delegated_tasks (tenant_id, id), \n\tCONSTRAINT fk_message_reply FOREIGN KEY(tenant_id, reply_to) REFERENCES conversation_messages (tenant_id, id), \n\tUNIQUE (tenant_id, conversation_id, sequence), \n\tUNIQUE (tenant_id, conversation_id, request_id)\n)')
    op.execute('CREATE TABLE task_progress (\n\ttenant_id VARCHAR NOT NULL, \n\tid VARCHAR NOT NULL, \n\ttask_id VARCHAR NOT NULL, \n\tkind VARCHAR NOT NULL, \n\tcontent VARCHAR NOT NULL, \n\tgeneration INTEGER NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (tenant_id, id), \n\tFOREIGN KEY(tenant_id, task_id) REFERENCES delegated_tasks (tenant_id, id)\n)')
    op.execute('CREATE TABLE work_events (\n\ttenant_id VARCHAR NOT NULL, \n\tid VARCHAR NOT NULL, \n\tconversation_id VARCHAR NOT NULL, \n\ttask_id VARCHAR, \n\tmessage_id VARCHAR, \n\tsequence INTEGER NOT NULL, \n\tkind VARCHAR NOT NULL, \n\tgeneration INTEGER NOT NULL, \n\tinstruction VARCHAR NOT NULL, \n\tattempts INTEGER NOT NULL, \n\tsources JSON NOT NULL, \n\thistory JSON NOT NULL, \n\tobservations JSON NOT NULL, \n\tusage JSON NOT NULL, \n\tlease_token VARCHAR, \n\tlease_until TIMESTAMP WITH TIME ZONE, \n\tpublished BOOLEAN NOT NULL, \n\tprocessed BOOLEAN NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (tenant_id, id), \n\tFOREIGN KEY(tenant_id, conversation_id) REFERENCES conversations (tenant_id, id), \n\tFOREIGN KEY(tenant_id, task_id) REFERENCES delegated_tasks (tenant_id, id), \n\tFOREIGN KEY(tenant_id, message_id) REFERENCES conversation_messages (tenant_id, id)\n)')


def downgrade():
    raise RuntimeError("Destructive downgrade disabled; restore an explicit backup")
