"""
drop reviews and bookmarks

both features are gone from the API and the UI, so their tables go too; downgrade recreates them empty

Revision ID: 93fc8a2cf8ea
Revises: 0bf062300ebc
Create Date: 2026-09-13 23:55:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '93fc8a2cf8ea'
down_revision: Union[str, None] = '0bf062300ebc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index('ix_workflow_item_reviews_item_status', table_name='workflow_item_reviews')
    op.drop_table('workflow_item_reviews')
    op.drop_index('ix_bookmarks_workflow_item', table_name='bookmarks')
    op.drop_table('bookmarks')


def downgrade() -> None:
    op.create_table('bookmarks',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('workflow_item_id', sa.UUID(), nullable=False),
    sa.Column('notes', sa.String(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['workflow_item_id'], ['workflow_items.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_bookmarks_workflow_item', 'bookmarks', ['workflow_item_id'], unique=False)
    op.create_table('workflow_item_reviews',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('workflow_item_id', sa.UUID(), nullable=False),
    sa.Column('review_status', sa.Enum('new', 'reviewed', 'item_of_interest', 'dismissed', 'false_positive', 'needs_follow_up', name='reviewstatus', native_enum=False, length=30), nullable=False),
    sa.Column('notes', sa.String(), nullable=True),
    sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['workflow_item_id'], ['workflow_items.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('workflow_item_id', name='uq_workflow_item_reviews_item')
    )
    op.create_index('ix_workflow_item_reviews_item_status', 'workflow_item_reviews', ['workflow_item_id', 'review_status'], unique=False)
