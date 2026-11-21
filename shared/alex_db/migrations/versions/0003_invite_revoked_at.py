"""invites can be withdrawn before they are used

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-14 08:00:00.000000
"""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("invites", sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("invites", "revoked_at")
