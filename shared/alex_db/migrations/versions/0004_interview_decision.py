"""hiring decision on an interview (advance / hold / reject)

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-14 22:00:00.000000
"""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("interviews", sa.Column("decision", sa.String(20), nullable=True))
    op.add_column("interviews", sa.Column("decision_note", sa.Text(), nullable=True))
    op.add_column(
        "interviews",
        sa.Column(
            "decided_by",
            sa.String(40),
            sa.ForeignKey("users.id", name="fk_interviews_decided_by_users", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "interviews", sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_check_constraint(
        "ck_interviews_decision",
        "interviews",
        "decision IS NULL OR decision IN ('advance', 'hold', 'reject')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_interviews_decision", "interviews", type_="check")
    op.drop_constraint("fk_interviews_decided_by_users", "interviews", type_="foreignkey")
    for column in ("decided_at", "decided_by", "decision_note", "decision"):
        op.drop_column("interviews", column)
