"""add_is_demo_to_workflows

Revision ID: 70c148fdfb53
Revises: 6bd9f67ec994
Create Date: 2026-05-29 20:40:36.303624

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '70c148fdfb53'
down_revision: Union[str, None] = '6bd9f67ec994'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('workflows', sa.Column('is_demo', sa.Boolean(), server_default=sa.text('false'), nullable=False))


def downgrade() -> None:
    op.drop_column('workflows', 'is_demo')
