"""ELO ranking and skill tree API routes.

Provides endpoints for:
- Viewing skill trees during and after interviews
- ELO rankings and leaderboards per role
- Candidate comparisons with skill breakdowns
- Role management for ELO grouping
"""

import json
import logging

from fastapi import APIRouter, Depends, HTTPException

from api.elo_schemas import (
    CandidateEloDetailResponse,
    EloComparisonResponse,
    EloRankingEntry,
    EloRankingsResponse,
    EvidenceCitationResponse,
    InterviewEloResult,
    MatchHistoryEntry,
    RoleInfo,
    RoleListResponse,
    SkillComparisonEntry,
    SkillEvidenceResponse,
    SkillLevel,
    SkillTreeDetailResponse,
    SkillTreeResponse,
)
from core.auth import User, ensure_session_user_access, require_user
from core.config import settings
from core.redis import get_redis_client
from core.roles import get_role

logger = logging.getLogger(__name__)

# Every endpoint is for signed-in recruiters, scoped to their organization
router = APIRouter(prefix="/elo", tags=["ELO Rankings"], dependencies=[Depends(require_user)])


async def _can_access_role(redis, role_id: str, user: User) -> bool:
    """Rankings belong to the organization that owns the job role."""
    role = await get_role(role_id)
    return user.can_access_org(role["org_id"] if role else None)


async def _ensure_role_access(redis, role_id: str, user: User) -> None:
    if not await _can_access_role(redis, role_id, user):
        raise HTTPException(status_code=404, detail=f"Role {role_id} not found")

# Redis key patterns (matching worker service)
CONTEXT_KEY_PREFIX = "context"
ELO_RATING_PREFIX = "elo_rating"
ELO_MATCH_PREFIX = "elo_match"
ROLE_CANDIDATES_PREFIX = "role_candidates"
SKILL_TREE_PREFIX = "skill_tree"
ROLE_LADDERS_PREFIX = "role_ladders"
WEIGHTED_SCORE_PREFIX = "weighted_score"

# ELO constants from config (matching worker scoring/elo_system.py)
DEFAULT_RATING = settings.elo_default_rating
MIN_CANDIDATES_FOR_RANKING = settings.elo_min_candidates_for_ranking


# =============================================================================
# Helper Functions
# =============================================================================


async def _get_session_state(redis, session_id: str) -> dict | None:
    """Get full session state from Redis hash."""
    key = f"{CONTEXT_KEY_PREFIX}:{session_id}"
    data = await redis.hgetall(key)

    if not data:
        return None

    state = {}
    for field, value in data.items():
        field_name = field.decode() if isinstance(field, bytes) else field
        value_str = value.decode() if isinstance(value, bytes) else value

        # Try to parse JSON for complex fields
        try:
            state[field_name] = json.loads(value_str)
        except (json.JSONDecodeError, TypeError):
            state[field_name] = value_str

    return state


async def _get_skill_tree_state(redis, session_id: str) -> dict | None:
    """Get skill tree state from session."""
    state = await _get_session_state(redis, session_id)
    if not state:
        return None
    return state.get("skill_tree")


async def _get_elo_rating(redis, candidate_id: str, role_id: str) -> dict | None:
    """Get ELO rating for a candidate in a role."""
    key = f"{ELO_RATING_PREFIX}:{role_id}:{candidate_id}"
    data = await redis.get(key)

    if not data:
        return None

    try:
        data_str = data.decode() if isinstance(data, bytes) else data
        return json.loads(data_str)
    except (json.JSONDecodeError, TypeError):
        return None


async def _get_role_candidates(redis, role_id: str) -> list[str]:
    """Get all candidate IDs for a role."""
    key = f"{ROLE_CANDIDATES_PREFIX}:{role_id}"
    members = await redis.smembers(key)
    return [m.decode() if isinstance(m, bytes) else m for m in members]


async def _get_all_roles(redis) -> list[str]:
    """Get all role IDs that have candidates."""
    roles = set()
    cursor = 0

    while True:
        cursor, keys = await redis.scan(
            cursor, match=f"{ROLE_CANDIDATES_PREFIX}:*", count=100
        )
        for key in keys:
            key_str = key.decode() if isinstance(key, bytes) else key
            role_id = key_str.split(":", 1)[1] if ":" in key_str else key_str
            roles.add(role_id)
        if cursor == 0:
            break

    return list(roles)


async def _get_match_history(redis, match_ids: list[str]) -> list[dict]:
    """Get match records by IDs."""
    matches = []
    for match_id in match_ids:
        key = f"{ELO_MATCH_PREFIX}:{match_id}"
        data = await redis.get(key)
        if data:
            try:
                data_str = data.decode() if isinstance(data, bytes) else data
                matches.append(json.loads(data_str))
            except (json.JSONDecodeError, TypeError):
                pass
    return matches


async def _get_skill_tree_from_storage(redis, session_id: str) -> dict | None:
    """Get persisted skill tree data."""
    key = f"{SKILL_TREE_PREFIX}:{session_id}"
    data = await redis.get(key)

    if not data:
        return None

    try:
        data_str = data.decode() if isinstance(data, bytes) else data
        return json.loads(data_str)
    except (json.JSONDecodeError, TypeError):
        return None


def _build_skill_tree_response(
    session_id: str, skill_tree_state: dict | None
) -> SkillTreeResponse:
    """Build SkillTreeResponse from skill tree state."""
    if not skill_tree_state or not skill_tree_state.get("tree_initialized"):
        return SkillTreeResponse(
            session_id=session_id,
            tree_initialized=False,
            skills=[],
        )

    current_levels = skill_tree_state.get("current_levels", {})
    skill_weights = skill_tree_state.get("skill_weights", {})
    evidence_counts = skill_tree_state.get("evidence_counts", {})

    skills = []
    for skill_name, level in current_levels.items():
        weight = skill_weights.get(skill_name, 0)
        evidence = evidence_counts.get(skill_name, 0)
        skills.append(
            SkillLevel(
                skill_name=skill_name,
                current_level=level,
                max_level=5,
                weight=weight,
                evidence_count=evidence,
                progress=(level / 5.0) * 100,
            )
        )

    # Sort by weight (highest first)
    skills.sort(key=lambda s: s.weight, reverse=True)

    total_skills = len(skills)
    assessed_skills = sum(1 for s in skills if s.current_level > 0)
    avg_level = (
        sum(s.current_level for s in skills) / total_skills if total_skills else 0
    )

    return SkillTreeResponse(
        session_id=session_id,
        role_id=skill_tree_state.get("role_id"),
        role_title=skill_tree_state.get("role_title"),
        tree_initialized=True,
        skills=skills,
        total_skills=total_skills,
        assessed_skills=assessed_skills,
        average_level=avg_level,
        weighted_score=skill_tree_state.get("weighted_score"),
        score_percentage=skill_tree_state.get("score_percentage"),
        next_suggested_skill=skill_tree_state.get("next_suggested_skill"),
        next_suggested_question=skill_tree_state.get("next_suggested_question"),
    )


def _calculate_percentile(rating: float, all_ratings: list[float]) -> float:
    """Calculate percentile rank for a rating.

    Note: This implementation must stay in sync with
    worker/scoring/elo_system.py:calculate_percentile()

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

    return (below + 0.5 * equal) / len(all_ratings) * 100


# =============================================================================
# Skill Tree Endpoints
# =============================================================================


@router.get("/skill-tree/{session_id}", response_model=SkillTreeResponse)
async def get_skill_tree(
    session_id: str, user: User = Depends(require_user)
) -> SkillTreeResponse:
    """Get real-time skill tree for an interview session.

    Returns the current state of skill assessment including levels,
    evidence counts, and next suggested question.
    """
    await ensure_session_user_access(session_id, user)
    async with get_redis_client() as redis:
        skill_tree_state = await _get_skill_tree_state(redis, session_id)
        return _build_skill_tree_response(session_id, skill_tree_state)


@router.get("/skill-tree/{session_id}/detail", response_model=SkillTreeDetailResponse)
async def get_skill_tree_detail(
    session_id: str, user: User = Depends(require_user)
) -> SkillTreeDetailResponse:
    """Get detailed skill tree with all evidence citations.

    Used for verification - shows all evidence supporting each skill level.
    """
    await ensure_session_user_access(session_id, user)
    async with get_redis_client() as redis:
        # Get session state
        state = await _get_session_state(redis, session_id)
        if not state:
            raise HTTPException(
                status_code=404, detail=f"Session {session_id} not found"
            )

        skill_tree_state = state.get("skill_tree")
        if not skill_tree_state or not skill_tree_state.get("tree_initialized"):
            raise HTTPException(
                status_code=404,
                detail=f"Skill tree not initialized for session {session_id}",
            )

        # Get persisted skill tree with evidence
        tree_data = await _get_skill_tree_from_storage(redis, session_id)

        skills_evidence = []
        total_evidence = 0

        if tree_data and "skills" in tree_data:
            for skill_name, skill_node in tree_data["skills"].items():
                evidence_by_level: dict[int, list[EvidenceCitationResponse]] = {}

                for level_str, citations in skill_node.get(
                    "evidence_by_level", {}
                ).items():
                    level = int(level_str)
                    evidence_by_level[level] = [
                        EvidenceCitationResponse(
                            level=c.get("level", level),
                            question_asked=c.get("question_asked", ""),
                            candidate_response=c.get("candidate_response", ""),
                            relevant_excerpt=c.get("relevant_excerpt", ""),
                            confidence=c.get("confidence", 0),
                            extracted_at=c.get("extracted_at", ""),
                        )
                        for c in citations
                    ]
                    total_evidence += len(citations)

                skills_evidence.append(
                    SkillEvidenceResponse(
                        skill_name=skill_name,
                        current_level=skill_node.get("current_level", 0),
                        evidence_by_level=evidence_by_level,
                    )
                )

        return SkillTreeDetailResponse(
            session_id=session_id,
            candidate_id=state.get("candidate_id", "unknown"),
            role_id=skill_tree_state.get("role_id", ""),
            role_title=skill_tree_state.get("role_title", ""),
            skills=skills_evidence,
            total_evidence_count=total_evidence,
            created_at=tree_data.get("created_at", "") if tree_data else "",
            last_updated=tree_data.get("last_updated", "") if tree_data else "",
        )


# =============================================================================
# Role Endpoints
# =============================================================================


@router.get("/roles", response_model=RoleListResponse)
async def list_roles(user: User = Depends(require_user)) -> RoleListResponse:
    """List the organization's roles that have candidates for ELO ranking."""
    async with get_redis_client() as redis:
        role_ids = [
            r for r in await _get_all_roles(redis) if await _can_access_role(redis, r, user)
        ]

        roles = []
        total_candidates = 0

        for role_id in role_ids:
            candidates = await _get_role_candidates(redis, role_id)
            count = len(candidates)
            total_candidates += count

            # Get top rating
            ratings = []
            for cid in candidates:
                rating_data = await _get_elo_rating(redis, cid, role_id)
                if rating_data:
                    ratings.append(rating_data.get("rating", DEFAULT_RATING))

            top_rating = max(ratings) if ratings else None
            avg_rating = sum(ratings) / len(ratings) if ratings else None

            # Try to get role title from a session
            role_title = None
            for cid in candidates[:1]:  # Just check first candidate
                # This would need session lookup - simplified here
                pass

            roles.append(
                RoleInfo(
                    role_id=role_id,
                    role_title=role_title,
                    candidate_count=count,
                    rankings_available=count >= MIN_CANDIDATES_FOR_RANKING,
                    top_rating=top_rating,
                    average_rating=avg_rating,
                )
            )

        # Sort by candidate count
        roles.sort(key=lambda r: r.candidate_count, reverse=True)

        return RoleListResponse(
            roles=roles,
            total_roles=len(roles),
            total_candidates=total_candidates,
        )


# =============================================================================
# Rankings Endpoints
# =============================================================================


@router.get("/rankings/{role_id}", response_model=EloRankingsResponse)
async def get_rankings(role_id: str, user: User = Depends(require_user)) -> EloRankingsResponse:
    """Get ELO leaderboard for a specific role.

    Rankings are only shown when 2+ candidates have been evaluated.
    """
    async with get_redis_client() as redis:
        await _ensure_role_access(redis, role_id, user)
        candidates = await _get_role_candidates(redis, role_id)

        if not candidates:
            return EloRankingsResponse(
                role_id=role_id,
                role_title=None,
                rankings=[],
                total_candidates=0,
                min_candidates_required=MIN_CANDIDATES_FOR_RANKING,
                rankings_available=False,
            )

        # Get all ratings
        rating_entries = []
        all_ratings = []

        for candidate_id in candidates:
            rating_data = await _get_elo_rating(redis, candidate_id, role_id)
            if rating_data:
                rating = rating_data.get("rating", DEFAULT_RATING)
                all_ratings.append(rating)
                rating_entries.append((candidate_id, rating_data))

        # Sort by rating
        rating_entries.sort(
            key=lambda x: x[1].get("rating", DEFAULT_RATING), reverse=True
        )

        # Build response
        rankings = []
        for rank, (candidate_id, data) in enumerate(rating_entries, 1):
            rating = data.get("rating", DEFAULT_RATING)
            percentile = _calculate_percentile(rating, all_ratings)

            rankings.append(
                EloRankingEntry(
                    candidate_id=candidate_id,
                    session_id=None,  # Could be retrieved from session mapping
                    rating=rating,
                    matches_played=data.get("matches_played", 0),
                    wins=data.get("wins", 0),
                    losses=data.get("losses", 0),
                    ties=data.get("ties", 0),
                    percentile=percentile,
                    rank=rank,
                    last_updated=data.get("last_updated"),
                )
            )

        # Get role title from first candidate's session if available
        role_title = None

        return EloRankingsResponse(
            role_id=role_id,
            role_title=role_title,
            rankings=rankings,
            total_candidates=len(candidates),
            min_candidates_required=MIN_CANDIDATES_FOR_RANKING,
            rankings_available=len(candidates) >= MIN_CANDIDATES_FOR_RANKING,
        )


@router.get(
    "/candidates/{candidate_id}/role/{role_id}",
    response_model=CandidateEloDetailResponse,
)
async def get_candidate_elo(
    candidate_id: str, role_id: str, user: User = Depends(require_user)
) -> CandidateEloDetailResponse:
    """Get detailed ELO information for a specific candidate."""
    async with get_redis_client() as redis:
        await _ensure_role_access(redis, role_id, user)
        rating_data = await _get_elo_rating(redis, candidate_id, role_id)

        if not rating_data:
            raise HTTPException(
                status_code=404,
                detail=f"No ELO rating found for candidate {candidate_id} in role {role_id}",
            )

        # Get all ratings for percentile calculation
        candidates = await _get_role_candidates(redis, role_id)
        all_ratings = []
        for cid in candidates:
            r = await _get_elo_rating(redis, cid, role_id)
            if r:
                all_ratings.append(r.get("rating", DEFAULT_RATING))

        rating = rating_data.get("rating", DEFAULT_RATING)
        percentile = _calculate_percentile(rating, all_ratings)

        # Calculate rank
        rank = sum(1 for r in all_ratings if r > rating) + 1

        # Get match history
        match_ids = rating_data.get("match_history", [])
        matches = await _get_match_history(redis, match_ids)

        match_history = []
        for match in matches:
            # Determine opponent and result
            if match.get("candidate_a_id") == candidate_id:
                opponent = match.get("candidate_b_id")
                rating_change = match.get("rating_change_a", 0)
                winner = match.get("winner_id")
                if winner == candidate_id:
                    result = "win"
                elif winner is None:
                    result = "tie"
                else:
                    result = "loss"
            else:
                opponent = match.get("candidate_a_id")
                rating_change = match.get("rating_change_b", 0)
                winner = match.get("winner_id")
                if winner == candidate_id:
                    result = "win"
                elif winner is None:
                    result = "tie"
                else:
                    result = "loss"

            match_history.append(
                MatchHistoryEntry(
                    match_id=match.get("match_id", ""),
                    opponent_id=opponent or "unknown",
                    result=result,
                    rating_change=rating_change,
                    rating_after=rating,  # Would need historical tracking
                    matched_at=match.get("matched_at", ""),
                )
            )

        return CandidateEloDetailResponse(
            candidate_id=candidate_id,
            role_id=role_id,
            rating=rating,
            percentile=percentile,
            rank=rank,
            matches_played=rating_data.get("matches_played", 0),
            wins=rating_data.get("wins", 0),
            losses=rating_data.get("losses", 0),
            ties=rating_data.get("ties", 0),
            match_history=match_history,
            skill_tree=None,  # Could be populated from session
            last_updated=rating_data.get("last_updated", ""),
        )


# =============================================================================
# Comparison Endpoints
# =============================================================================


@router.get(
    "/compare/{role_id}/{candidate_a_id}/{candidate_b_id}",
    response_model=EloComparisonResponse,
)
async def compare_candidates(
    role_id: str, candidate_a_id: str, candidate_b_id: str, user: User = Depends(require_user)
) -> EloComparisonResponse:
    """Compare two candidates side-by-side with skill breakdown."""
    async with get_redis_client() as redis:
        await _ensure_role_access(redis, role_id, user)
        # Get ratings
        rating_a = await _get_elo_rating(redis, candidate_a_id, role_id)
        rating_b = await _get_elo_rating(redis, candidate_b_id, role_id)

        if not rating_a:
            raise HTTPException(
                status_code=404,
                detail=f"Candidate {candidate_a_id} not found in role {role_id}",
            )
        if not rating_b:
            raise HTTPException(
                status_code=404,
                detail=f"Candidate {candidate_b_id} not found in role {role_id}",
            )

        # Get weighted scores for skill comparison
        score_a_key = f"{WEIGHTED_SCORE_PREFIX}:{role_id}:{candidate_a_id}"
        score_b_key = f"{WEIGHTED_SCORE_PREFIX}:{role_id}:{candidate_b_id}"

        score_a_data = await redis.get(score_a_key)
        score_b_data = await redis.get(score_b_key)

        skill_comparisons = []
        total_a = 0.0
        total_b = 0.0

        if score_a_data and score_b_data:
            try:
                score_a = json.loads(
                    score_a_data.decode()
                    if isinstance(score_a_data, bytes)
                    else score_a_data
                )
                score_b = json.loads(
                    score_b_data.decode()
                    if isinstance(score_b_data, bytes)
                    else score_b_data
                )

                # Build skill maps
                skills_a = {s["skill_name"]: s for s in score_a.get("skill_scores", [])}
                skills_b = {s["skill_name"]: s for s in score_b.get("skill_scores", [])}

                all_skills = set(skills_a.keys()) | set(skills_b.keys())

                for skill_name in all_skills:
                    s_a = skills_a.get(skill_name, {})
                    s_b = skills_b.get(skill_name, {})

                    level_a = s_a.get("achieved_level", 0)
                    level_b = s_b.get("achieved_level", 0)
                    weight = s_a.get("weight", 0) or s_b.get("weight", 0)

                    if level_a > level_b:
                        winner = "a"
                    elif level_b > level_a:
                        winner = "b"
                    else:
                        winner = "tie"

                    skill_comparisons.append(
                        SkillComparisonEntry(
                            skill_name=skill_name,
                            level_a=level_a,
                            level_b=level_b,
                            weight=weight,
                            winner=winner,
                        )
                    )

                total_a = score_a.get("total_weighted_score", 0)
                total_b = score_b.get("total_weighted_score", 0)

            except (json.JSONDecodeError, TypeError):
                pass

        # Sort by weight
        skill_comparisons.sort(key=lambda s: s.weight, reverse=True)

        # Determine overall winner
        if total_a > total_b:
            overall_winner = "a"
        elif total_b > total_a:
            overall_winner = "b"
        else:
            overall_winner = "tie"

        return EloComparisonResponse(
            candidate_a_id=candidate_a_id,
            candidate_b_id=candidate_b_id,
            candidate_a_rating=rating_a.get("rating", DEFAULT_RATING),
            candidate_b_rating=rating_b.get("rating", DEFAULT_RATING),
            skill_comparisons=skill_comparisons,
            total_a=total_a,
            total_b=total_b,
            overall_winner=overall_winner,
            rating_change_a=None,
            rating_change_b=None,
        )


# =============================================================================
# Interview Result Endpoint
# =============================================================================


@router.get("/interview-result/{session_id}", response_model=InterviewEloResult)
async def get_interview_elo_result(
    session_id: str, user: User = Depends(require_user)
) -> InterviewEloResult:
    """Get complete ELO result after interview completion.

    Includes skill tree, evidence, ELO rating, and leaderboard position.
    """
    await ensure_session_user_access(session_id, user)
    async with get_redis_client() as redis:
        # Get session state
        state = await _get_session_state(redis, session_id)
        if not state:
            raise HTTPException(
                status_code=404, detail=f"Session {session_id} not found"
            )

        skill_tree_state = state.get("skill_tree")
        if not skill_tree_state:
            raise HTTPException(
                status_code=404, detail=f"No skill tree found for session {session_id}"
            )

        role_id = skill_tree_state.get("role_id", "")
        candidate_id = state.get("candidate_id", "unknown")

        # Build skill tree response
        skill_tree = _build_skill_tree_response(session_id, skill_tree_state)

        # Get skill evidence
        tree_data = await _get_skill_tree_from_storage(redis, session_id)
        skills_evidence = []

        if tree_data and "skills" in tree_data:
            for skill_name, skill_node in tree_data["skills"].items():
                evidence_by_level: dict[int, list[EvidenceCitationResponse]] = {}

                for level_str, citations in skill_node.get(
                    "evidence_by_level", {}
                ).items():
                    level = int(level_str)
                    evidence_by_level[level] = [
                        EvidenceCitationResponse(
                            level=c.get("level", level),
                            question_asked=c.get("question_asked", ""),
                            candidate_response=c.get("candidate_response", ""),
                            relevant_excerpt=c.get("relevant_excerpt", ""),
                            confidence=c.get("confidence", 0),
                            extracted_at=c.get("extracted_at", ""),
                        )
                        for c in citations
                    ]

                skills_evidence.append(
                    SkillEvidenceResponse(
                        skill_name=skill_name,
                        current_level=skill_node.get("current_level", 0),
                        evidence_by_level=evidence_by_level,
                    )
                )

        # Get ELO rating
        rating_data = await _get_elo_rating(redis, candidate_id, role_id)
        elo_rating = (
            rating_data.get("rating", DEFAULT_RATING) if rating_data else DEFAULT_RATING
        )
        matches_played = rating_data.get("matches_played", 0) if rating_data else 0

        # Get all candidates for percentile and ranking
        candidates = await _get_role_candidates(redis, role_id)
        all_ratings = []
        for cid in candidates:
            r = await _get_elo_rating(redis, cid, role_id)
            if r:
                all_ratings.append(r.get("rating", DEFAULT_RATING))

        percentile = (
            _calculate_percentile(elo_rating, all_ratings) if all_ratings else None
        )
        rank = (
            sum(1 for r in all_ratings if r > elo_rating) + 1 if all_ratings else None
        )

        # Get leaderboard if available
        leaderboard = None
        if len(candidates) >= MIN_CANDIDATES_FOR_RANKING:
            rankings_response = await get_rankings(role_id)
            leaderboard = rankings_response.rankings

        return InterviewEloResult(
            candidate_id=candidate_id,
            session_id=session_id,
            role_id=role_id,
            role_title=skill_tree_state.get("role_title"),
            skill_tree=skill_tree,
            skill_evidence=skills_evidence,
            elo_rating=elo_rating,
            elo_percentile=percentile,
            rank=rank,
            total_candidates=len(candidates),
            matches_played=matches_played,
            rankings_available=len(candidates) >= MIN_CANDIDATES_FOR_RANKING,
            leaderboard=leaderboard,
        )
