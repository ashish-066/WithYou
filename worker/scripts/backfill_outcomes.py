"""Copy outcomes of ended interviews from Redis into Postgres.

For interviews that ended before outcomes were saved to Postgres (or whose
save failed — the worker logs "FAILED to save interview outcome"). Safe to
re-run: it upserts.

    uv run python -m scripts.backfill_outcomes            # copy
    uv run python -m scripts.backfill_outcomes --dry-run  # only list
"""

import argparse
import asyncio
import sys

from alex_db import dispose_engine

from core.redis import close_redis_pool, get_redis_client
from services.interview_store import save_interview_outcome
from services.state_manager import ContextManager
from services.transcript import load_transcript


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    redis = await get_redis_client()
    contexts = ContextManager(redis)
    ended = skipped = failed = 0
    async for key in redis.scan_iter(match="context:*", count=200):
        session_id = key.split(":", 1)[1]
        state = await contexts.get_context(session_id)
        if not state.get("interview_ended"):
            skipped += 1
            continue
        ended += 1
        if args.dry_run:
            print(f"would copy {session_id}")
        elif await save_interview_outcome(
            session_id, state, await load_transcript(redis, session_id)
        ):
            print(f"copied {session_id}")
        else:
            failed += 1

    print(f"ended: {ended}, still in progress (skipped): {skipped}, failed: {failed}")
    await close_redis_pool()
    await dispose_engine()
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
