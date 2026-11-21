"""study sessions: language and starting topic (plus the learner who owns it)

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-22 02:00:00.000000
"""

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("interviews", sa.Column("language", sa.String(10), nullable=True))
    op.add_column("interviews", sa.Column("topic", sa.String(200), nullable=True))
    op.add_column("interviews", sa.Column("user_id", sa.String(40), nullable=True))
    op.create_index("ix_interviews_user_created", "interviews", ["user_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_interviews_user_created", table_name="interviews")
    for column in ("user_id", "topic", "language"):
        op.drop_column("interviews", column)
