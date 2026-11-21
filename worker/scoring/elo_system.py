"""Elo Rating System for candidate comparison.

This module implements an Elo-based ranking system that:
1. Compares candidates based on skill tree comparisons
2. Maintains persistent Elo ratings per role
3. Provides transparent match breakdowns
4. Only shows rankings after 2+ candidates have been evaluated
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Literal

from redis.asyncio import Redis

from scoring.models import (
    ComparisonBreakdown,
    EloMatch,
    EloRating,
    RoleRequirements,
    SkillComparison,
    WeightedScore,
)
from scoring.score_calculator import ScoreCalculator

logger = logging.getLogger(__name__)


class EloSystem:
    """Elo rating system for comparing and ranking candidates.

    Uses the standard Elo formula with adjustable K-factor.
    Ratings are persisted in Redis per role.
    """

    # Redis key patterns
    RATING_KEY_PREFIX = "elo_rating"
    MATCH_KEY_PREFIX = "elo_match"
    ROLE_CANDIDATES_KEY_PREFIX = "role_candidates"

    # Elo configuration
    DEFAULT_RATING = 1500.0
    K_FACTOR = 32.0  # Standard K-factor
    MIN_CANDIDATES_FOR_RANKING = 2

    def __init__(
        self,
        redis: Redis,
        score_calculator: ScoreCalculator | None = None,
        k_factor: float = 32.0,
    ):
        """Initialize the Elo system.

        Args:
            redis: Async Redis client
            score_calculator: Score calculator for comparisons
            k_factor: Elo K-factor (higher = more volatile ratings)
        """
        self.redis = redis
        self.score_calculator = score_calculator or ScoreCalculator()
        self.k_factor = k_factor

    # =========================================================================
    # Key Generation
    # =========================================================================

    def _rating_key(self, candidate_id: str, role_id: str) -> str:
        """Generate Redis key for a candidate's Elo rating."""
        return f"{self.RATING_KEY_PREFIX}:{role_id}:{candidate_id}"

    def _match_key(self, match_id: str) -> str:
        """Generate Redis key for a match record."""
        return f"{self.MATCH_KEY_PREFIX}:{match_id}"

    def _role_candidates_key(self, role_id: str) -> str:
        """Generate Redis key for role's candidate list."""
        return f"{self.ROLE_CANDIDATES_KEY_PREFIX}:{role_id}"

    # =========================================================================
    # Rating Operations
    # =========================================================================

    async def get_rating(self, candidate_id: str, role_id: str) -> EloRating:
        """Get a candidate's Elo rating for a role.

        Args:
            candidate_id: Candidate identifier
            role_id: Role identifier

        Returns:
            EloRating (existing or default)
        """
        rating_key = self._rating_key(candidate_id, role_id)
        data = await self.redis.get(rating_key)

        if data:
            try:
                if isinstance(data, bytes):
                    data = data.decode("utf-8")
                return EloRating.model_validate_json(data)
            except Exception as e:
                logger.error(f"Failed to deserialize rating: {e}")

        # Return default rating
        return EloRating(
            candidate_id=candidate_id,
            role_id=role_id,
            rating=self.DEFAULT_RATING,
        )

    async def save_rating(self, rating: EloRating) -> None:
        """Save a candidate's Elo rating.

        Args:
            rating: EloRating to save
        """
        rating_key = self._rating_key(rating.candidate_id, rating.role_id)
        rating.last_updated = datetime.now(timezone.utc).isoformat()
        await self.redis.set(rating_key, rating.model_dump_json())

        # Track candidate in role's candidate set
        role_candidates_key = self._role_candidates_key(rating.role_id)
        await self.redis.sadd(role_candidates_key, rating.candidate_id)

    async def get_match(self, match_id: str) -> EloMatch | None:
        """Get a match record by ID.

        Args:
            match_id: Match identifier

        Returns:
            EloMatch or None
        """
        match_key = self._match_key(match_id)
        data = await self.redis.get(match_key)

        if data:
            try:
                if isinstance(data, bytes):
                    data = data.decode("utf-8")
                return EloMatch.model_validate_json(data)
            except Exception as e:
                logger.error(f"Failed to deserialize match: {e}")

        return None

    async def save_match(self, match: EloMatch) -> None:
        """Save a match record.

        Args:
            match: EloMatch to save
        """
        match_key = self._match_key(match.match_id)
        await self.redis.set(match_key, match.model_dump_json())

    # =========================================================================
    # Comparison Operations
    # =========================================================================

    def compare_candidates(
        self,
        score_a: WeightedScore,
        score_b: WeightedScore,
        requirements: RoleRequirements,
    ) -> ComparisonBreakdown:
        """Compare two candidates based on their weighted scores.

        Args:
            score_a: First candidate's score
            score_b: Second candidate's score
            requirements: Role requirements

        Returns:
            ComparisonBreakdown with per-skill results
        """
        # Build skill maps
        skills_a = {s.skill_name: s for s in score_a.skill_scores}
        skills_b = {s.skill_name: s for s in score_b.skill_scores}

        skill_comparisons = []

        for skill_req in requirements.skills:
            skill_name = skill_req.skill_name
            weight = skill_req.weight

            s_a = skills_a.get(skill_name)
            s_b = skills_b.get(skill_name)

            level_a = s_a.achieved_level if s_a else 0
            level_b = s_b.achieved_level if s_b else 0

            if level_a > level_b:
                winner: Literal["a", "b", "tie"] = "a"
            elif level_b > level_a:
                winner = "b"
            else:
                winner = "tie"

            skill_comparisons.append(
                SkillComparison(
                    skill_name=skill_name,
                    candidate_a_level=level_a,
                    candidate_b_level=level_b,
                    weight=weight,
                    winner=winner,
                )
            )

        # Determine overall winner
        total_a = score_a.total_weighted_score
        total_b = score_b.total_weighted_score

        if total_a > total_b:
            overall_winner: Literal["a", "b", "tie"] = "a"
        elif total_b > total_a:
            overall_winner = "b"
        else:
            overall_winner = "tie"

        return ComparisonBreakdown(
            skill_comparisons=skill_comparisons,
            total_a=total_a,
            total_b=total_b,
            winner=overall_winner,
        )

    def calculate_elo_change(
        self,
        rating_a: float,
        rating_b: float,
        result: Literal["a", "b", "tie"],
    ) -> tuple[float, float]:
        """Calculate Elo rating changes after a match.

        Uses standard Elo formula:
        E_a = 1 / (1 + 10^((R_b - R_a) / 400))
        R'_a = R_a + K * (S_a - E_a)

        Args:
            rating_a: Current rating of candidate A
            rating_b: Current rating of candidate B
            result: Match result ("a" wins, "b" wins, or "tie")

        Returns:
            (change_a, change_b) rating changes
        """
        # Calculate expected scores
        expected_a = 1 / (1 + 10 ** ((rating_b - rating_a) / 400))
        expected_b = 1 - expected_a

        # Actual scores
        if result == "a":
            actual_a, actual_b = 1.0, 0.0
        elif result == "b":
            actual_a, actual_b = 0.0, 1.0
        else:  # tie
            actual_a, actual_b = 0.5, 0.5

        # Calculate changes
        change_a = self.k_factor * (actual_a - expected_a)
        change_b = self.k_factor * (actual_b - expected_b)

        return (change_a, change_b)

    async def record_match(
        self,
        score_a: WeightedScore,
        score_b: WeightedScore,
        requirements: RoleRequirements,
    ) -> EloMatch:
        """Record a match between two candidates and update ratings.

        Args:
            score_a: First candidate's score
            score_b: Second candidate's score
            requirements: Role requirements

        Returns:
            EloMatch record
        """
        candidate_a = score_a.candidate_id
        candidate_b = score_b.candidate_id
        role_id = score_a.role_id

        # Get current ratings
        rating_a = await self.get_rating(candidate_a, role_id)
        rating_b = await self.get_rating(candidate_b, role_id)

        # Compare candidates
        breakdown = self.compare_candidates(score_a, score_b, requirements)

        # Calculate rating changes
        change_a, change_b = self.calculate_elo_change(
            rating_a.rating, rating_b.rating, breakdown.winner
        )

        # Determine winner ID
        if breakdown.winner == "a":
            winner_id = candidate_a
        elif breakdown.winner == "b":
            winner_id = candidate_b
        else:
            winner_id = None

        # Create match record
        match_id = str(uuid.uuid4())
        match = EloMatch(
            match_id=match_id,
            candidate_a_id=candidate_a,
            candidate_b_id=candidate_b,
            winner_id=winner_id,
            rating_change_a=change_a,
            rating_change_b=change_b,
            breakdown=breakdown,
        )

        # Update ratings
        rating_a.rating += change_a
        rating_a.matches_played += 1
        rating_a.match_history.append(match_id)
        if breakdown.winner == "a":
            rating_a.wins += 1
        elif breakdown.winner == "b":
            rating_a.losses += 1
        else:
            rating_a.ties += 1

        rating_b.rating += change_b
        rating_b.matches_played += 1
        rating_b.match_history.append(match_id)
        if breakdown.winner == "b":
            rating_b.wins += 1
        elif breakdown.winner == "a":
            rating_b.losses += 1
        else:
            rating_b.ties += 1

        # Save everything
        await self.save_rating(rating_a)
        await self.save_rating(rating_b)
        await self.save_match(match)

        logger.info(
            f"Match recorded: {candidate_a} vs {candidate_b}, "
            f"winner={breakdown.winner}, changes=({change_a:+.1f}, {change_b:+.1f})"
        )

        return match

    # =========================================================================
    # Ranking Operations
    # =========================================================================

    async def get_role_rankings(
        self,
        role_id: str,
    ) -> list[EloRating] | None:
        """Get rankings for all candidates in a role.

        Returns None if fewer than MIN_CANDIDATES_FOR_RANKING candidates.

        Args:
            role_id: Role identifier

        Returns:
            List of EloRating sorted by rating (descending), or None
        """
        role_candidates_key = self._role_candidates_key(role_id)
        candidate_ids = await self.redis.smembers(role_candidates_key)

        if not candidate_ids:
            return None

        # Decode bytes
        candidate_ids = [c.decode("utf-8") if isinstance(c, bytes) else c for c in candidate_ids]

        if len(candidate_ids) < self.MIN_CANDIDATES_FOR_RANKING:
            logger.debug(
                f"Only {len(candidate_ids)} candidates for role {role_id}, "
                f"need {self.MIN_CANDIDATES_FOR_RANKING} for rankings"
            )
            return None

        # Get all ratings
        ratings = []
        for candidate_id in candidate_ids:
            rating = await self.get_rating(candidate_id, role_id)
            ratings.append(rating)

        # Sort by rating (descending)
        ratings.sort(key=lambda r: r.rating, reverse=True)

        return ratings

    async def get_candidate_count(self, role_id: str) -> int:
        """Get number of candidates evaluated for a role.

        Args:
            role_id: Role identifier

        Returns:
            Candidate count
        """
        role_candidates_key = self._role_candidates_key(role_id)
        return await self.redis.scard(role_candidates_key)

    async def can_show_rankings(self, role_id: str) -> bool:
        """Check if rankings can be shown for a role.

        Args:
            role_id: Role identifier

        Returns:
            True if enough candidates for rankings
        """
        count = await self.get_candidate_count(role_id)
        return count >= self.MIN_CANDIDATES_FOR_RANKING

    # =========================================================================
    # Match Comparison for New Candidate
    # =========================================================================

    async def compare_against_pool(
        self,
        new_score: WeightedScore,
        requirements: RoleRequirements,
        max_comparisons: int = 5,
    ) -> list[EloMatch]:
        """Compare a new candidate against the existing candidate pool.

        Args:
            new_score: New candidate's score
            requirements: Role requirements
            max_comparisons: Maximum comparisons to make

        Returns:
            List of EloMatch records
        """
        role_id = new_score.role_id
        candidate_id = new_score.candidate_id

        # Get existing candidates
        role_candidates_key = self._role_candidates_key(role_id)
        existing_ids = await self.redis.smembers(role_candidates_key)

        if not existing_ids:
            # First candidate - just save rating
            rating = EloRating(
                candidate_id=candidate_id,
                role_id=role_id,
                rating=self.DEFAULT_RATING,
            )
            await self.save_rating(rating)
            return []

        # Decode bytes
        existing_ids = [c.decode("utf-8") if isinstance(c, bytes) else c for c in existing_ids]

        # Remove self if already in pool
        existing_ids = [c for c in existing_ids if c != candidate_id]

        if not existing_ids:
            return []

        # Limit comparisons
        if len(existing_ids) > max_comparisons:
            # Compare against highest-rated candidates
            ratings = []
            for cid in existing_ids:
                r = await self.get_rating(cid, role_id)
                ratings.append((cid, r.rating))
            ratings.sort(key=lambda x: x[1], reverse=True)
            existing_ids = [r[0] for r in ratings[:max_comparisons]]

        # Note: We need the existing candidates' scores to compare
        # This would require fetching their skill trees and recalculating
        # For now, this is a placeholder - in practice, you'd store scores
        # or recalculate from saved skill trees

        logger.info(f"Would compare {candidate_id} against {len(existing_ids)} candidates")

        # Return empty for now - full implementation would fetch stored scores
        return []


# =============================================================================
# Utility Functions
# =============================================================================


def format_rankings_for_display(rankings: list[EloRating]) -> str:
    """Format rankings for text display.

    Args:
        rankings: List of EloRating sorted by rating

    Returns:
        Formatted string
    """
    lines = ["Candidate Rankings:", ""]

    for i, rating in enumerate(rankings, 1):
        record = f"{rating.wins}W-{rating.losses}L-{rating.ties}T"
        lines.append(f"  {i}. {rating.candidate_id}: {rating.rating:.0f} ({record})")

    return "\n".join(lines)


def format_match_for_display(match: EloMatch) -> str:
    """Format a match for text display.

    Args:
        match: EloMatch to format

    Returns:
        Formatted string
    """
    lines = [
        f"Match: {match.candidate_a_id} vs {match.candidate_b_id}",
        f"Winner: {match.winner_id or 'Tie'}",
        f"Rating Changes: A={match.rating_change_a:+.1f}, B={match.rating_change_b:+.1f}",
        "",
        "Skill Breakdown:",
    ]

    for comp in match.breakdown.skill_comparisons:
        winner_mark = {
            "a": "◀",
            "b": "▶",
            "tie": "=",
        }[comp.winner]

        lines.append(
            f"  {comp.skill_name} (w={comp.weight:.0%}): "
            f"L{comp.candidate_a_level} {winner_mark} L{comp.candidate_b_level}"
        )

    lines.append("")
    lines.append(f"Total: {match.breakdown.total_a:.3f} vs {match.breakdown.total_b:.3f}")

    return "\n".join(lines)


def calculate_percentile(rating: float, all_ratings: list[float]) -> float:
    """Calculate percentile rank for a rating.

    Args:
        rating: Rating to check
        all_ratings: All ratings in the pool

    Returns:
        Percentile (0-100)
    """
    if not all_ratings:
        return 50.0

    below = sum(1 for r in all_ratings if r < rating)
    equal = sum(1 for r in all_ratings if r == rating)

    percentile = (below + 0.5 * equal) / len(all_ratings) * 100
    return percentile
