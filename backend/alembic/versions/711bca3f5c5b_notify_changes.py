"""
notify changes

triggers that announce writes to the tables the UI renders on the geotriage_changes channel,
which the API relays to browsers over its websocket (see api/live.py)

triggers rather than calls in the pipeline, so nothing that writes these tables can forget to announce it
Postgres drops identical payloads within one transaction, so a payload names what changed and nothing more:
- workflows fire on insert, update and delete
- workflow_items and model_runs fire on insert and update only,
  they are deleted solely by cascade from a workflow, which announces itself
- the job queue fires once per statement, since the only thing watching it is a summary view

Revision ID: 711bca3f5c5b
Revises: ad330ec33788
Create Date: 2026-09-13 18:05:12.000000
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '711bca3f5c5b'
down_revision: Union[str, None] = 'ad330ec33788'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


FUNCTIONS = {
    'notify_workflow_change': """
        DECLARE r workflows%ROWTYPE;
        BEGIN
            r := CASE TG_OP WHEN 'DELETE' THEN OLD ELSE NEW END;
            PERFORM pg_notify('geotriage_changes', jsonb_build_object('topic', 'workflow', 'id', r.id)::text);
            RETURN NULL;
        END
    """,
    'notify_workflow_item_change': """
        BEGIN
            PERFORM pg_notify(
                'geotriage_changes',
                jsonb_build_object('topic', 'workflow_item', 'id', NEW.id, 'workflow_id', NEW.workflow_id)::text
            );
            RETURN NULL;
        END
    """,
    'notify_model_run_change': """
        BEGIN
            PERFORM pg_notify(
                'geotriage_changes',
                jsonb_build_object(
                    'topic', 'model_run',
                    'id', NEW.id,
                    'workflow_item_id', NEW.workflow_item_id,
                    'workflow_id', (SELECT workflow_id FROM workflow_items WHERE id = NEW.workflow_item_id)
                )::text
            );
            RETURN NULL;
        END
    """,
    # TG_ARGV[0] is 'model' or 'provider'
    'notify_registry_change': """
        BEGIN
            PERFORM pg_notify('geotriage_changes', jsonb_build_object('topic', 'registry', 'kind', TG_ARGV[0])::text);
            RETURN NULL;
        END
    """,
    'notify_queue_change': """
        BEGIN
            PERFORM pg_notify('geotriage_changes', jsonb_build_object('topic', 'queue')::text);
            RETURN NULL;
        END
    """,
}

# (trigger, table, events, granularity, function call)
TRIGGERS = [
    ('trg_workflows_notify', 'workflows', 'INSERT OR UPDATE OR DELETE', 'ROW', 'notify_workflow_change()'),
    ('trg_workflow_items_notify', 'workflow_items', 'INSERT OR UPDATE', 'ROW', 'notify_workflow_item_change()'),
    ('trg_model_runs_notify', 'model_runs', 'INSERT OR UPDATE', 'ROW', 'notify_model_run_change()'),
    ('trg_registered_models_notify', 'registered_models', 'INSERT OR UPDATE OR DELETE', 'ROW', "notify_registry_change('model')"),
    ('trg_registered_providers_notify', 'registered_providers', 'INSERT OR UPDATE OR DELETE', 'ROW', "notify_registry_change('provider')"),
    ('trg_jobs_notify', 'jobs', 'INSERT OR UPDATE OR DELETE', 'STATEMENT', 'notify_queue_change()'),
]


def upgrade() -> None:
    for name, body in FUNCTIONS.items():
        op.execute(f"CREATE FUNCTION {name}() RETURNS trigger LANGUAGE plpgsql AS $${body}$$")
    for trigger, table, events, granularity, call in TRIGGERS:
        op.execute(f"CREATE TRIGGER {trigger} AFTER {events} ON {table} FOR EACH {granularity} EXECUTE FUNCTION {call}")


def downgrade() -> None:
    for trigger, table, _events, _granularity, _call in TRIGGERS:
        op.execute(f"DROP TRIGGER IF EXISTS {trigger} ON {table}")
    for name in FUNCTIONS:
        op.execute(f"DROP FUNCTION IF EXISTS {name}()")
