"""Readiness file for container health checks.

The worker has no HTTP server. Once set up (Redis reachable, schema current,
consumer group joined) it touches READY_FILE, then again after every
successful heartbeat. The container health check runs

    python -m core.readiness

which passes while the file is fresh, so a worker whose Redis connection is
gone stops reporting ready within MAX_AGE_SECONDS.
"""

import os
import sys
import time
from pathlib import Path

READY_FILE = Path(os.getenv("WORKER_READY_FILE", "/tmp/alex-worker-ready"))
MAX_AGE_SECONDS = 60


def mark_ready() -> None:
    READY_FILE.touch()


def mark_not_ready() -> None:
    READY_FILE.unlink(missing_ok=True)


def is_ready(max_age_seconds: float = MAX_AGE_SECONDS) -> bool:
    try:
        return time.time() - READY_FILE.stat().st_mtime < max_age_seconds
    except FileNotFoundError:
        return False


if __name__ == "__main__":
    sys.exit(0 if is_ready() else 1)
