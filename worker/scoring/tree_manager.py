"""Skill Tree Manager with Redis persistence and distributed locking.

This module manages candidate skill trees in Redis, providing:
1. Atomic read/write operations for skill trees
2. Distributed locking to prevent race conditions
3. Methods to update skill levels with evidence
4. Batch operations for efficiency
"""

import asyncio
import json
import logging
import secrets
from datetime import datetime, timezone
from typing import Any

from redis.asyncio import Redis

from scoring.models import (
    CandidateSkillTree,
    EvidenceCitation,
    EvidenceExtraction,
    QAExchange,
    RoleRequirements,
    SkillLadder,
    SkillTreeNode,
)

logger = logging.getLogger(__name__)


class TreeLockError(Exception):
    """Raised when a skill tree lock cannot be acquired."""

    pass


class SkillTreeManager:
    """Manages candidate skill trees in Redis with distributed locking.

    Provides atomic operations for reading, updating, and persisting
    skill trees during interview sessions.

    Usage:
        manager = SkillTreeManager(redis_client)

        # Get or create a skill tree
        tree = await manager.get_or_create_tree(
            candidate_id="cand_123",
            session_id="sess_456",
            role_id="role_789",
            skills=["Python", "AWS", "SQL"]
        )

        # Update with evidence (acquires lock automatically)
        await manager.update_skill_with_evidence(
            session_id="sess_456",
            skill_name="Python",
            level=3,
            evidence=citation
        )
    """

    # Redis key patterns
    TREE_KEY_PREFIX = "skilltree"
    LOCK_KEY_PREFIX = "skilltree_lock"
    ROLE_LADDERS_KEY_PREFIX = "role_ladders"

    # Lock configuration
    LOCK_TTL_MS = 5000  # 5 seconds
    LOCK_RETRY_DELAY_MS = 100
    LOCK_MAX_RETRIES = 50

    def __init__(self, redis: Redis, confidence_threshold: float = 0.7):
        """Initialize the skill tree manager.

        Args:
            redis: Async Redis client
            confidence_threshold: Minimum confidence to confirm a level
        """
        self.redis = redis
        self.confidence_threshold = confidence_threshold

    # =========================================================================
    # Key Generation
    # =========================================================================

    def _tree_key(self, session_id: str) -> str:
        """Generate Redis key for a skill tree."""
        return f"{self.TREE_KEY_PREFIX}:{session_id}"

    def _lock_key(self, session_id: str) -> str:
        """Generate Redis key for a skill tree lock."""
        return f"{self.LOCK_KEY_PREFIX}:{session_id}"

    def _ladders_key(self, role_id: str) -> str:
        """Generate Redis key for role skill ladders."""
        return f"{self.ROLE_LADDERS_KEY_PREFIX}:{role_id}"

    # =========================================================================
    # Locking Operations
    # =========================================================================

    async def acquire_lock(
        self,
        session_id: str,
        ttl_ms: int | None = None,
        blocking: bool = True,
    ) -> str | None:
        """Acquire a distributed lock for a skill tree.

        Args:
            session_id: Session to lock
            ttl_ms: Lock TTL in milliseconds
            blocking: Whether to retry until lock is acquired

        Returns:
            Lock token if acquired, None if non-blocking and unavailable
        """
        lock_key = self._lock_key(session_id)
        ttl = ttl_ms or self.LOCK_TTL_MS
        lock_token = secrets.token_hex(16)

        retries = 0
        while True:
            acquired = await self.redis.set(
                lock_key,
                lock_token,
                nx=True,
                px=ttl,
            )

            if acquired:
                logger.debug(f"Skill tree lock acquired for session {session_id}")
                return lock_token

            if not blocking:
                return None

            retries += 1
            if retries >= self.LOCK_MAX_RETRIES:
                raise TreeLockError(
                    f"Failed to acquire skill tree lock for session {session_id} "
                    f"after {retries} retries"
                )

            await self._sleep_ms(self.LOCK_RETRY_DELAY_MS)

    async def release_lock(self, session_id: str, lock_token: str) -> bool:
        """Release a skill tree lock.

        Args:
            session_id: Session to unlock
            lock_token: Token from acquire_lock

        Returns:
            True if released, False if token mismatch
        """
        lock_key = self._lock_key(session_id)

        lua_script = """
        if redis.call("GET", KEYS[1]) == ARGV[1] then
            return redis.call("DEL", KEYS[1])
        else
            return 0
        end
        """

        result = await self.redis.eval(lua_script, 1, lock_key, lock_token)
        released = result == 1

        if released:
            logger.debug(f"Skill tree lock released for session {session_id}")
        else:
            logger.warning(f"Failed to release skill tree lock for session {session_id}")

        return released

    # =========================================================================
    # Tree CRUD Operations
    # =========================================================================

    async def get_tree(self, session_id: str) -> CandidateSkillTree | None:
        """Get a skill tree from Redis.

        Args:
            session_id: Session to get tree for

        Returns:
            CandidateSkillTree or None if not found
        """
        tree_key = self._tree_key(session_id)
        data = await self.redis.get(tree_key)

        if not data:
            return None

        try:
            if isinstance(data, bytes):
                data = data.decode("utf-8")
            return CandidateSkillTree.model_validate_json(data)
        except Exception as e:
            logger.error(f"Failed to deserialize skill tree for {session_id}: {e}")
            return None

    async def save_tree(self, tree: CandidateSkillTree) -> None:
        """Save a skill tree to Redis.

        Args:
            tree: CandidateSkillTree to save
        """
        tree_key = self._tree_key(tree.session_id)
        tree.last_updated = datetime.now(timezone.utc).isoformat()

        await self.redis.set(tree_key, tree.model_dump_json())
        logger.debug(f"Skill tree saved for session {tree.session_id}")

    async def delete_tree(self, session_id: str) -> bool:
        """Delete a skill tree from Redis.

        Args:
            session_id: Session to delete tree for

        Returns:
            True if deleted, False if not found
        """
        tree_key = self._tree_key(session_id)
        result = await self.redis.delete(tree_key)
        return result > 0

    async def get_or_create_tree(
        self,
        candidate_id: str,
        session_id: str,
        role_id: str,
        skills: list[str],
    ) -> CandidateSkillTree:
        """Get existing tree or create a new one.

        Args:
            candidate_id: Candidate identifier
            session_id: Session identifier
            role_id: Role identifier
            skills: List of skill names to initialize

        Returns:
            CandidateSkillTree (existing or newly created)
        """
        tree = await self.get_tree(session_id)

        if tree:
            # Ensure all skills exist in tree
            for skill in skills:
                tree.get_or_create_skill(skill)
            return tree

        # Create new tree with initialized skills
        tree = CandidateSkillTree(
            candidate_id=candidate_id,
            session_id=session_id,
            role_id=role_id,
        )

        for skill in skills:
            tree.skills[skill] = SkillTreeNode(skill_name=skill)

        await self.save_tree(tree)
        logger.info(f"Created new skill tree for session {session_id} with {len(skills)} skills")

        return tree

    # =========================================================================
    # Skill Update Operations
    # =========================================================================

    async def update_skill_with_evidence(
        self,
        session_id: str,
        skill_name: str,
        level: int,
        evidence: EvidenceCitation,
    ) -> CandidateSkillTree:
        """Update a skill with new evidence (with automatic locking).

        Args:
            session_id: Session identifier
            skill_name: Skill to update
            level: Level that evidence supports
            evidence: Evidence citation

        Returns:
            Updated CandidateSkillTree
        """
        lock_token = await self.acquire_lock(session_id)
        try:
            tree = await self.get_tree(session_id)
            if not tree:
                raise ValueError(f"No skill tree found for session {session_id}")

            tree.update_skill_level(skill_name, level, evidence)
            await self.save_tree(tree)

            logger.info(
                f"Updated {skill_name} to level {level} for session {session_id} "
                f"with confidence {evidence.confidence:.2f}"
            )

            return tree

        finally:
            await self.release_lock(session_id, lock_token)

    async def apply_extractions(
        self,
        session_id: str,
        extractions: list[EvidenceExtraction],
        exchange: QAExchange,
    ) -> CandidateSkillTree:
        """Apply multiple evidence extractions to a skill tree.

        Only applies extractions that are:
        - Answer is "Yes"
        - Confidence >= threshold

        Args:
            session_id: Session identifier
            extractions: List of evidence extractions
            exchange: The Q&A exchange that produced these extractions

        Returns:
            Updated CandidateSkillTree
        """
        lock_token = await self.acquire_lock(session_id)
        try:
            tree = await self.get_tree(session_id)
            if not tree:
                raise ValueError(f"No skill tree found for session {session_id}")

            updates_made = 0

            for extraction in extractions:
                # Only apply confirmed extractions above threshold
                if extraction.answer != "Yes":
                    continue
                if extraction.confidence < self.confidence_threshold:
                    logger.debug(
                        f"Skipping {extraction.skill_name} L{extraction.level}: "
                        f"confidence {extraction.confidence:.2f} < {self.confidence_threshold}"
                    )
                    continue

                # Create evidence citation
                citation = EvidenceCitation(
                    level=extraction.level,
                    question_asked=exchange.interviewer_question,
                    candidate_response=exchange.candidate_response,
                    relevant_excerpt=extraction.evidence,
                    confidence=extraction.confidence,
                )

                # Update the skill tree
                tree.update_skill_level(extraction.skill_name, extraction.level, citation)
                updates_made += 1

                logger.debug(
                    f"Applied evidence for {extraction.skill_name} L{extraction.level} "
                    f"(confidence: {extraction.confidence:.2f})"
                )

            if updates_made > 0:
                await self.save_tree(tree)
                logger.info(f"Applied {updates_made} evidence updates for session {session_id}")

            return tree

        finally:
            await self.release_lock(session_id, lock_token)

    # =========================================================================
    # Skill Ladder Operations
    # =========================================================================

    async def save_role_ladders(
        self,
        role_id: str,
        ladders: dict[str, SkillLadder],
    ) -> None:
        """Save skill ladders for a role.

        Args:
            role_id: Role identifier
            ladders: Dict of skill name to SkillLadder
        """
        ladders_key = self._ladders_key(role_id)
        serialized = {name: ladder.model_dump_json() for name, ladder in ladders.items()}
        await self.redis.set(ladders_key, json.dumps(serialized))
        logger.info(f"Saved {len(ladders)} skill ladders for role {role_id}")

    async def get_role_ladders(self, role_id: str) -> dict[str, SkillLadder] | None:
        """Get skill ladders for a role.

        Args:
            role_id: Role identifier

        Returns:
            Dict of skill name to SkillLadder, or None if not found
        """
        ladders_key = self._ladders_key(role_id)
        data = await self.redis.get(ladders_key)

        if not data:
            return None

        try:
            if isinstance(data, bytes):
                data = data.decode("utf-8")
            serialized = json.loads(data)
            return {
                name: SkillLadder.model_validate_json(ladder_json)
                for name, ladder_json in serialized.items()
            }
        except Exception as e:
            logger.error(f"Failed to deserialize ladders for role {role_id}: {e}")
            return None

    # =========================================================================
    # Query Operations
    # =========================================================================

    def get_current_levels(self, tree: CandidateSkillTree) -> dict[str, int]:
        """Get current skill levels from a tree.

        Args:
            tree: CandidateSkillTree

        Returns:
            Dict mapping skill name to current level
        """
        return {name: node.current_level for name, node in tree.skills.items()}

    def get_skills_needing_assessment(
        self,
        tree: CandidateSkillTree,
        requirements: RoleRequirements,
        max_skills: int = 3,
    ) -> list[tuple[str, float, int]]:
        """Get skills that need assessment, prioritized by weight and gap.

        Args:
            tree: CandidateSkillTree
            requirements: RoleRequirements with skill weights
            max_skills: Maximum number of skills to return

        Returns:
            List of (skill_name, weight, current_level) tuples, sorted by priority
        """
        skill_weights = {s.skill_name: s.weight for s in requirements.skills}
        priorities = []

        for skill_name, weight in skill_weights.items():
            node = tree.skills.get(skill_name)
            current_level = node.current_level if node else 0

            # Priority = weight * remaining_potential
            remaining_potential = 5 - current_level
            if remaining_potential > 0:
                priority = weight * remaining_potential
                priorities.append((skill_name, weight, current_level, priority))

        # Sort by priority (descending)
        priorities.sort(key=lambda x: x[3], reverse=True)

        return [(s[0], s[1], s[2]) for s in priorities[:max_skills]]

    def calculate_tree_completeness(
        self,
        tree: CandidateSkillTree,
        requirements: RoleRequirements,
    ) -> float:
        """Calculate how complete the skill tree assessment is.

        Args:
            tree: CandidateSkillTree
            requirements: RoleRequirements

        Returns:
            Completeness score (0.0 - 1.0)
        """
        if not requirements.skills:
            return 1.0

        total_weighted_progress = 0.0
        total_weight = 0.0

        for skill in requirements.skills:
            node = tree.skills.get(skill.skill_name)
            current_level = node.current_level if node else 0

            # Progress is current_level / max_level (5)
            progress = current_level / 5.0
            total_weighted_progress += progress * skill.weight
            total_weight += skill.weight

        return total_weighted_progress / total_weight if total_weight > 0 else 0.0

    # =========================================================================
    # Utilities
    # =========================================================================

    async def _sleep_ms(self, ms: int) -> None:
        """Async sleep for milliseconds."""
        await asyncio.sleep(ms / 1000)


# =============================================================================
# Utility Functions
# =============================================================================


def serialize_tree_for_api(tree: CandidateSkillTree) -> dict[str, Any]:
    """Serialize a skill tree for API response.

    Args:
        tree: CandidateSkillTree

    Returns:
        Dict suitable for JSON API response
    """
    skills_summary = []

    for name, node in tree.skills.items():
        skills_summary.append(
            {
                "skill_name": name,
                "current_level": node.current_level,
                "max_level": node.max_possible_level,
                "evidence_count": node.get_total_evidence(),
                "last_assessed": node.last_assessed_at,
            }
        )

    return {
        "candidate_id": tree.candidate_id,
        "session_id": tree.session_id,
        "role_id": tree.role_id,
        "skills": skills_summary,
        "created_at": tree.created_at,
        "last_updated": tree.last_updated,
    }


def get_tree_visualization_data(tree: CandidateSkillTree) -> dict[str, Any]:
    """Get data formatted for frontend skill tree visualization.

    Args:
        tree: CandidateSkillTree

    Returns:
        Dict with visualization-ready data
    """
    nodes = []
    for name, skill_node in tree.skills.items():
        node_data = {
            "id": name,
            "name": name,
            "level": skill_node.current_level,
            "maxLevel": skill_node.max_possible_level,
            "progress": skill_node.current_level / skill_node.max_possible_level,
            "evidenceByLevel": {},
        }

        # Add evidence summaries per level
        for level, citations in skill_node.evidence_by_level.items():
            node_data["evidenceByLevel"][level] = [
                {
                    "excerpt": c.relevant_excerpt,
                    "confidence": c.confidence,
                    "timestamp": c.extracted_at,
                }
                for c in citations
            ]

        nodes.append(node_data)

    return {
        "candidateId": tree.candidate_id,
        "sessionId": tree.session_id,
        "roleId": tree.role_id,
        "nodes": nodes,
        "lastUpdated": tree.last_updated,
    }
