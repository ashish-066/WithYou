"""DSA Problem Store — Redis CRUD for DSA problem packets.

Problem packets are stored as Redis hashes under the key:
    dsa_problem:{problem_id}

An index of all problem IDs is maintained at:
    dsa_problem:index  (Redis set)

This follows the exact same pattern as job_role:{role_id} in
avatar/api/role_routes.py and avatar/api/admin_schemas.py.

The full DSAProblem (including reference solution, hidden tests,
rubric, etc.) is stored server-side only and NEVER sent to the
candidate. The DSAProblemPublic view is used for candidate-facing APIs.
"""

import json
import logging
from typing import Any

from redis.asyncio import Redis

from dsa.models import DSAProblem, DSAProblemPublic

logger = logging.getLogger(__name__)

# Redis key constants
PROBLEM_KEY_PREFIX = "dsa_problem"
PROBLEM_INDEX_KEY = f"{PROBLEM_KEY_PREFIX}:index"


class DSAProblemStore:
    """Async Redis-backed store for DSA problem packets."""

    def __init__(self, redis: Redis):
        self.redis = redis

    # =========================================================================
    # Internal helpers
    # =========================================================================

    def _key(self, problem_id: str) -> str:
        return f"{PROBLEM_KEY_PREFIX}:{problem_id}"

    async def _save(self, problem: DSAProblem) -> None:
        """Serialize a DSAProblem to a Redis hash."""
        key = self._key(problem.problem_id)
        # Store the entire model as a single JSON field inside the hash.
        # This is simpler and safer than flattening nested structures.
        await self.redis.hset(
            key,
            mapping={
                "problem_id": problem.problem_id,
                "title": problem.title,
                "difficulty": problem.difficulty,
                "tags": json.dumps(problem.tags),
                "created_at": problem.created_at,
                "created_by": problem.created_by,
                # Full model stored as JSON for lossless round-trip
                "_data": problem.model_dump_json(),
            },
        )
        # Add to index
        await self.redis.sadd(PROBLEM_INDEX_KEY, problem.problem_id)

    async def _load(self, problem_id: str) -> DSAProblem | None:
        """Deserialize a DSAProblem from a Redis hash."""
        key = self._key(problem_id)
        data = await self.redis.hget(key, "_data")
        if not data:
            return None
        try:
            return DSAProblem.model_validate_json(data)
        except Exception as e:
            logger.error(f"Failed to deserialize DSAProblem {problem_id}: {e}")
            return None

    # =========================================================================
    # Public API
    # =========================================================================

    async def create(self, problem: DSAProblem) -> DSAProblem:
        """Create a new DSA problem.

        Raises:
            ValueError: If a problem with the same problem_id already exists.
        """
        key = self._key(problem.problem_id)
        exists = await self.redis.exists(key)
        if exists:
            raise ValueError(
                f"DSA problem with ID '{problem.problem_id}' already exists"
            )
        await self._save(problem)
        logger.info(f"Created DSA problem: {problem.problem_id} ({problem.title})")
        return problem

    async def get(self, problem_id: str) -> DSAProblem | None:
        """Fetch the full DSA problem (server-side, includes reference solution)."""
        return await self._load(problem_id)

    async def get_public(self, problem_id: str) -> DSAProblemPublic | None:
        """Fetch candidate-safe view of a problem (strips reference solution etc.)."""
        problem = await self._load(problem_id)
        if not problem:
            return None
        return DSAProblemPublic(
            problem_id=problem.problem_id,
            title=problem.title,
            statement=problem.statement,
            constraints=problem.constraints,
            difficulty=problem.difficulty,
            tags=problem.tags,
            public_test_cases=problem.public_test_cases,
        )

    async def update(self, problem: DSAProblem) -> DSAProblem:
        """Update an existing DSA problem."""
        key = self._key(problem.problem_id)
        exists = await self.redis.exists(key)
        if not exists:
            raise ValueError(
                f"DSA problem with ID '{problem.problem_id}' not found"
            )
        await self._save(problem)
        logger.info(f"Updated DSA problem: {problem.problem_id}")
        return problem

    async def delete(self, problem_id: str) -> bool:
        """Delete a DSA problem."""
        key = self._key(problem_id)
        deleted = await self.redis.delete(key)
        await self.redis.srem(PROBLEM_INDEX_KEY, problem_id)
        if deleted:
            logger.info(f"Deleted DSA problem: {problem_id}")
        return deleted > 0

    async def list_all(self) -> list[dict[str, Any]]:
        """List all DSA problems (metadata only — title, difficulty, tags, created_at)."""
        problem_ids = await self.redis.smembers(PROBLEM_INDEX_KEY)
        results = []

        for pid in problem_ids:
            key = self._key(pid)
            meta = await self.redis.hmget(
                key, "problem_id", "title", "difficulty", "tags", "created_at", "created_by"
            )
            if meta and meta[0]:  # problem_id is not None
                results.append(
                    {
                        "problem_id": meta[0],
                        "title": meta[1] or "",
                        "difficulty": meta[2] or "medium",
                        "tags": json.loads(meta[3]) if meta[3] else [],
                        "created_at": meta[4] or "",
                        "created_by": meta[5] or "admin",
                    }
                )

        return sorted(results, key=lambda x: x.get("created_at", ""), reverse=True)

    async def exists(self, problem_id: str) -> bool:
        """Check if a problem exists."""
        key = self._key(problem_id)
        return bool(await self.redis.exists(key))
