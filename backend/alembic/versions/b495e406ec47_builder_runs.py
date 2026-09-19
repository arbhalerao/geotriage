"""
builder runs

one row per turn of a workflow builder conversation, announced on the changes channel like the other tables the UI renders,
so a browser waiting on a draft hears each step and the answer as they land

Revision ID: b495e406ec47
Revises: ca48c08b8836
Create Date: 2026-09-14 15:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'b495e406ec47'
down_revision: Union[str, None] = 'ca48c08b8836'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


NOTIFY = """
    BEGIN
        PERFORM pg_notify('geotriage_changes', jsonb_build_object('topic', 'builder_run', 'id', NEW.id)::text);
        RETURN NULL;
    END
"""


def upgrade() -> None:
    op.create_table('builder_runs',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('status', sa.Enum('queued', 'running', 'done', 'failed', name='builderrunstatus', native_enum=False, length=10), nullable=False),
    sa.Column('conversation', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('steps', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('outcome', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('error', sa.String(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.execute(f"CREATE FUNCTION notify_builder_run_change() RETURNS trigger LANGUAGE plpgsql AS $${NOTIFY}$$")
    op.execute("CREATE TRIGGER trg_builder_runs_notify AFTER INSERT OR UPDATE ON builder_runs FOR EACH ROW EXECUTE FUNCTION notify_builder_run_change()")


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_builder_runs_notify ON builder_runs")
    op.execute("DROP FUNCTION IF EXISTS notify_builder_run_change()")
    op.drop_table('builder_runs')
