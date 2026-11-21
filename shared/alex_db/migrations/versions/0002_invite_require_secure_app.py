"""invites can require the locked desktop app

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-07 01:30:00.000000
"""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "invites",
        sa.Column("require_secure_app", sa.Boolean(), server_default=sa.false(), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("invites", "require_secure_app")
