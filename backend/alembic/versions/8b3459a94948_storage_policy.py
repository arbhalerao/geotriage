"""
storage policy

what a workflow's scenes keep once scored, and what each scene has left; existing workflows keep everything,
which is how they behaved before policies existed, and existing scenes are marked as not yet applied

Revision ID: 8b3459a94948
Revises: cb07ffa143c3
Create Date: 2026-09-14 22:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '8b3459a94948'
down_revision: Union[str, None] = 'cb07ffa143c3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('workflows', sa.Column('storage_policy', sa.Enum('everything', 'alert_and_caution_in_full', 'alert_in_full', 'results_only', 'scores_only', name='storagepolicy', native_enum=False, length=30), server_default='everything', nullable=False))
    op.add_column('workflow_items', sa.Column('imagery_kept', sa.Enum('inputs_and_results', 'results', 'none', name='imagerykept', native_enum=False, length=20), nullable=True))


def downgrade() -> None:
    op.drop_column('workflow_items', 'imagery_kept')
    op.drop_column('workflows', 'storage_policy')
