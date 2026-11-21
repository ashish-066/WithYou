"""Pydantic models for ELO ranking and skill tree API endpoints.

This module defines all request/response schemas for the ELO system,
including rankings, comparisons, and skill tree visualization.
"""

from typing import Literal

from pydantic import BaseModel, Field

# =============================================================================
# Skill Tree Schemas
# =============================================================================


class SkillLevel(BaseModel):
    """A single skill with its current assessed level."""

    skill_name: str = Field(description="Name of the skill")
    current_level: int = Field(ge=0, le=5, description="Current level (0-5)")
    max_level: int = Field(default=5, description="Maximum level")
    weight: float = Field(ge=0, le=1, description="Weight for this role")
    evidence_count: int = Field(default=0, description="Number of evidence citations")
    progress: float = Field(description="Progress percentage (0-100)")


class SkillTreeResponse(BaseModel):
    """Response containing skill tree visualization data."""

    session_id: str = Field(description="Interview session ID")
    role_id: str | None = Field(default=None, description="Role identifier")
    role_title: str | None = Field(default=None, description="Role title")
    tree_initialized: bool = Field(description="Whether tree has been initialized")
    skills: list[SkillLevel] = Field(default_factory=list, description="Skill levels")
    total_skills: int = Field(default=0, description="Total number of skills")
    assessed_skills: int = Field(default=0, description="Number of assessed skills")
    average_level: float = Field(default=0.0, description="Average skill level")
    weighted_score: float | None = Field(
        default=None, description="Weighted score (0-5)"
    )
    score_percentage: float | None = Field(
        default=None, description="Score as percentage"
    )
    next_suggested_skill: str | None = Field(
        default=None, description="Next skill to probe"
    )
    next_suggested_question: str | None = Field(
        default=None, description="Suggested question"
    )


class EvidenceCitationResponse(BaseModel):
    """A piece of evidence supporting a skill level."""

    level: int = Field(description="Skill level this supports")
    question_asked: str = Field(description="Question that elicited evidence")
    candidate_response: str = Field(description="Candidate's response")
    relevant_excerpt: str = Field(description="Specific supporting excerpt")
    confidence: float = Field(description="Confidence score")
    extracted_at: str = Field(description="When extracted")


class SkillEvidenceResponse(BaseModel):
    """Evidence breakdown for a single skill."""

    skill_name: str = Field(description="Skill name")
    current_level: int = Field(description="Current assessed level")
    evidence_by_level: dict[int, list[EvidenceCitationResponse]] = Field(
        default_factory=dict, description="Evidence citations by level"
    )


class SkillTreeDetailResponse(BaseModel):
    """Detailed skill tree with all evidence for verification."""

    session_id: str
    candidate_id: str
    role_id: str
    role_title: str
    skills: list[SkillEvidenceResponse]
    total_evidence_count: int
    created_at: str
    last_updated: str


# =============================================================================
# ELO Ranking Schemas
# =============================================================================


class EloRankingEntry(BaseModel):
    """A single entry in the ELO leaderboard."""

    candidate_id: str = Field(description="Candidate identifier")
    session_id: str | None = Field(default=None, description="Latest session ID")
    rating: float = Field(description="Current ELO rating")
    matches_played: int = Field(default=0, description="Total matches")
    wins: int = Field(default=0, description="Wins")
    losses: int = Field(default=0, description="Losses")
    ties: int = Field(default=0, description="Ties")
    percentile: float | None = Field(default=None, description="Percentile rank")
    rank: int | None = Field(default=None, description="Rank position")
    last_updated: str | None = Field(default=None, description="Last rating update")


class EloRankingsResponse(BaseModel):
    """Response containing ELO leaderboard for a role."""

    role_id: str = Field(description="Role identifier")
    role_title: str | None = Field(default=None, description="Role title")
    rankings: list[EloRankingEntry] = Field(description="Ranked candidates")
    total_candidates: int = Field(description="Total candidates evaluated")
    min_candidates_required: int = Field(default=2, description="Min for rankings")
    rankings_available: bool = Field(description="Whether rankings can be shown")


# =============================================================================
# Comparison Schemas
# =============================================================================


class SkillComparisonEntry(BaseModel):
    """Comparison of two candidates on a single skill."""

    skill_name: str = Field(description="Skill name")
    level_a: int = Field(ge=0, le=5, description="Candidate A level")
    level_b: int = Field(ge=0, le=5, description="Candidate B level")
    weight: float = Field(description="Skill weight")
    winner: Literal["a", "b", "tie"] = Field(description="Who won this skill")


class EloComparisonResponse(BaseModel):
    """Response containing comparison between two candidates."""

    candidate_a_id: str = Field(description="First candidate ID")
    candidate_b_id: str = Field(description="Second candidate ID")
    candidate_a_rating: float = Field(description="Candidate A ELO rating")
    candidate_b_rating: float = Field(description="Candidate B ELO rating")
    skill_comparisons: list[SkillComparisonEntry] = Field(
        description="Per-skill comparison"
    )
    total_a: float = Field(description="Candidate A weighted score")
    total_b: float = Field(description="Candidate B weighted score")
    overall_winner: Literal["a", "b", "tie"] = Field(description="Overall winner")
    rating_change_a: float | None = Field(default=None, description="A's rating change")
    rating_change_b: float | None = Field(default=None, description="B's rating change")


# =============================================================================
# Match History Schemas
# =============================================================================


class MatchHistoryEntry(BaseModel):
    """A single match in candidate's history."""

    match_id: str = Field(description="Match identifier")
    opponent_id: str = Field(description="Opponent candidate ID")
    result: Literal["win", "loss", "tie"] = Field(description="Match result")
    rating_change: float = Field(description="Rating change from this match")
    rating_after: float = Field(description="Rating after this match")
    matched_at: str = Field(description="When match occurred")


class CandidateEloDetailResponse(BaseModel):
    """Detailed ELO information for a single candidate."""

    candidate_id: str
    role_id: str
    rating: float
    percentile: float | None
    rank: int | None
    matches_played: int
    wins: int
    losses: int
    ties: int
    match_history: list[MatchHistoryEntry]
    skill_tree: SkillTreeResponse | None
    last_updated: str


# =============================================================================
# Role Schemas
# =============================================================================


class RoleInfo(BaseModel):
    """Information about a role with candidates."""

    role_id: str = Field(description="Role identifier")
    role_title: str | None = Field(default=None, description="Role title")
    candidate_count: int = Field(description="Number of candidates")
    rankings_available: bool = Field(description="Whether rankings can be shown")
    top_rating: float | None = Field(default=None, description="Highest rating")
    average_rating: float | None = Field(default=None, description="Average rating")


class RoleListResponse(BaseModel):
    """Response containing all roles with candidates."""

    roles: list[RoleInfo] = Field(description="List of roles")
    total_roles: int = Field(description="Total number of roles")
    total_candidates: int = Field(description="Total candidates across all roles")


# =============================================================================
# Request Schemas
# =============================================================================


class CompareRequest(BaseModel):
    """Request to compare two candidates."""

    candidate_a_id: str = Field(description="First candidate ID")
    candidate_b_id: str = Field(description="Second candidate ID")
    role_id: str = Field(description="Role to compare for")


# =============================================================================
# Interview Result with ELO
# =============================================================================


class InterviewEloResult(BaseModel):
    """ELO result shown after interview completion."""

    candidate_id: str
    session_id: str
    role_id: str
    role_title: str | None

    # Skill tree summary
    skill_tree: SkillTreeResponse
    skill_evidence: list[SkillEvidenceResponse]

    # ELO results
    elo_rating: float
    elo_percentile: float | None
    rank: int | None
    total_candidates: int
    matches_played: int

    # Comparison with others
    rankings_available: bool
    leaderboard: list[EloRankingEntry] | None
