"""candidate background on the invite (links, resume and LinkedIn export text)

The organization already has the candidate's resume and profiles, so they come
with the invite instead of being asked from the candidate at the interview.

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-15 12:00:00.000000
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("invites", sa.Column("github_url", sa.String(500), nullable=True))
    op.add_column("invites", sa.Column("linkedin_url", sa.String(500), nullable=True))
    op.add_column("invites", sa.Column("other_links", JSONB(), nullable=True))
    op.add_column("invites", sa.Column("resume_text", sa.Text(), nullable=True))
    op.add_column("invites", sa.Column("linkedin_text", sa.Text(), nullable=True))


def downgrade() -> None:
    for column in ("linkedin_text", "resume_text", "other_links", "linkedin_url", "github_url"):
        op.drop_column("invites", column)
