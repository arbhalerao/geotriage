"""
llm calls

one row per request to a language model, for tracing the workflow builder

Revision ID: ca48c08b8836
Revises: 93fc8a2cf8ea
Create Date: 2026-09-14 12:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'ca48c08b8836'
down_revision: Union[str, None] = '93fc8a2cf8ea'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('llm_calls',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('purpose', sa.String(), nullable=False),
    sa.Column('model', sa.String(), nullable=False),
    sa.Column('prompt_version', sa.String(), nullable=True),
    sa.Column('job_id', sa.UUID(), nullable=True),
    sa.Column('outcome', sa.Enum('ok', 'error', name='llmcalloutcome', native_enum=False, length=10), nullable=False),
    sa.Column('error', sa.String(), nullable=True),
    sa.Column('input_tokens', sa.Integer(), nullable=False),
    sa.Column('output_tokens', sa.Integer(), nullable=False),
    sa.Column('duration_ms', sa.Integer(), nullable=False),
    sa.Column('request', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('response', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_llm_calls_purpose_created', 'llm_calls', ['purpose', 'created_at'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_llm_calls_purpose_created', table_name='llm_calls')
    op.drop_table('llm_calls')
