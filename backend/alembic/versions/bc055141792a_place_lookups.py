"""
place lookups

OpenStreetMap answers for the builder's place queries, shared by every worker and kept across restarts

Revision ID: bc055141792a
Revises: b495e406ec47
Create Date: 2026-09-14 20:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'bc055141792a'
down_revision: Union[str, None] = 'b495e406ec47'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('place_lookups',
    sa.Column('query_key', sa.String(), nullable=False),
    sa.Column('query', sa.String(), nullable=False),
    sa.Column('candidates', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('looked_up_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('query_key')
    )


def downgrade() -> None:
    op.drop_table('place_lookups')
