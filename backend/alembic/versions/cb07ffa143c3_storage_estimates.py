"""
storage estimates

estimates of the scenes and data a workflow would stage, asked for on the form and worked on the worker,
announced on the changes channel so the form hears the result

Revision ID: cb07ffa143c3
Revises: bc055141792a
Create Date: 2026-09-14 21:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'cb07ffa143c3'
down_revision: Union[str, None] = 'bc055141792a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


NOTIFY = """
    BEGIN
        PERFORM pg_notify('geotriage_changes', jsonb_build_object('topic', 'storage_estimate', 'id', NEW.id)::text);
        RETURN NULL;
    END
"""


def upgrade() -> None:
    op.create_table('storage_estimates',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('status', sa.Enum('queued', 'running', 'done', 'failed', name='builderrunstatus', native_enum=False, length=10), nullable=False),
    sa.Column('draft', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('result', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('error', sa.String(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.execute(f"CREATE FUNCTION notify_storage_estimate_change() RETURNS trigger LANGUAGE plpgsql AS $${NOTIFY}$$")
    op.execute("CREATE TRIGGER trg_storage_estimates_notify AFTER INSERT OR UPDATE ON storage_estimates FOR EACH ROW EXECUTE FUNCTION notify_storage_estimate_change()")


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_storage_estimates_notify ON storage_estimates")
    op.execute("DROP FUNCTION IF EXISTS notify_storage_estimate_change()")
    op.drop_table('storage_estimates')
