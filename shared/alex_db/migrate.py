"""Run database migrations.

    DATABASE_URL=postgresql://... python -m alex_db.migrate            # upgrade to latest
    DATABASE_URL=postgresql://... python -m alex_db.migrate downgrade -1

Run this before starting new service versions (a deploy step in Phase 3).
"""

import sys
from pathlib import Path

from alembic import command
from alembic.config import Config

from alex_db.session import database_url

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


def alembic_config(url: str | None = None) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS_DIR))
    cfg.set_main_option("sqlalchemy.url", (url or database_url()).replace("%", "%%"))
    return cfg


def upgrade(url: str | None = None, revision: str = "head") -> None:
    command.upgrade(alembic_config(url), revision)


def downgrade(url: str | None = None, revision: str = "-1") -> None:
    command.downgrade(alembic_config(url), revision)


if __name__ == "__main__":
    args = sys.argv[1:]
    if args[:1] == ["downgrade"]:
        downgrade(revision=args[1] if len(args) > 1 else "-1")
    else:
        upgrade(revision=args[1] if args[:1] == ["upgrade"] and len(args) > 1 else "head")
