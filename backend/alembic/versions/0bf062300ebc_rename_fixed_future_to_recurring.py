"""
rename fixed_future to recurring

the time mode is stored as a plain string with no database constraint on its values (see core/db/models/enums.py),
so the rename is a data update and nothing about the column changes

Revision ID: 0bf062300ebc
Revises: 711bca3f5c5b
Create Date: 2026-09-13 22:40:00.000000
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0bf062300ebc'
down_revision: Union[str, None] = '711bca3f5c5b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("UPDATE workflows SET time_mode = 'recurring' WHERE time_mode = 'fixed_future'")


def downgrade() -> None:
    op.execute("UPDATE workflows SET time_mode = 'fixed_future' WHERE time_mode = 'recurring'")
