"""Pydantic models for the Evidence-Based Skill Tree Scoring System.

This module defines all data structures used throughout the scoring system,
ensuring type safety and validation.
"""

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

# =============================================================================
# Phase 1: JD Parsing & Skill Ladder Models
# =============================================================================


class SkillRequirement(BaseModel):
    """A skill requirement extracted from a job description.

    Attributes:
        skill_name: Name of the skill (e.g., "Distributed Caching")
        weight: Importance weight for this role (0-1, sums to 1 across all skills)
        related_skills: Skills that can transfer knowledge (e.g., GCP for AWS role)
        context: Additional context from the JD about this skill requirement
    """

    skill_name: str = Field(description="Name of the skill")
    weight: float = Field(ge=0.0, le=1.0, description="Importance weight (0-1)")
    related_skills: list[str] = Field(
        default_factory=list, description="Related skills for transferability"
    )
    context: str = Field(default="", description="Context from JD about this skill")


class RoleRequirements(BaseModel):
    """Structured requirements extracted from a job description.

    Attributes:
        title: Job title
        skills: List of skill requirements with weights
        total_skills: Number of skills (for validation)
    """

    title: str = Field(description="Job title from the JD")
    skills: list[SkillRequirement] = Field(description="Skill requirements with weights")

    def validate_weights(self) -> bool:
        """Ensure weights sum to approximately 1.0."""
        total = sum(s.weight for s in self.skills)
        return 0.95 <= total <= 1.05


class LadderLevel(BaseModel):
    """A single level in a skill depth ladder.

    Each level represents increasing competency, answered by a binary question.

    Attributes:
        level: Level number (1-5)
        binary_question: Y/N question to determine if this level is achieved
        evidence_hints: Phrases/concepts that would indicate a Yes answer
        example_yes: Example response that would be a Yes
        example_no: Example response that would be a No
    """

    level: int = Field(ge=1, le=5, description="Depth level (1=awareness, 5=mastery)")
    binary_question: str = Field(description="Y/N question for this level")
    evidence_hints: list[str] = Field(default_factory=list, description="Phrases indicating Yes")
    example_yes: str = Field(default="", description="Example of a Yes response")
    example_no: str = Field(default="", description="Example of a No response")


class SkillLadder(BaseModel):
    """A complete depth ladder for a skill.

    Contains 5 levels of binary questions, from awareness to mastery.

    Attributes:
        skill_name: Name of the skill this ladder evaluates
        levels: List of 5 LadderLevel objects
        generated_at: Timestamp when this ladder was generated
    """

    skill_name: str = Field(description="Skill this ladder evaluates")
    levels: list[LadderLevel] = Field(description="5 depth levels")
    generated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def get_level(self, level_num: int) -> LadderLevel | None:
        """Get a specific level by number."""
        for level in self.levels:
            if level.level == level_num:
                return level
        return None


class SkillTransferability(BaseModel):
    """Defines how experience in one skill transfers to another.

    Used to fairly evaluate candidates with equivalent but not identical experience.

    Attributes:
        from_skill: Source skill (e.g., "GCP")
        to_skill: Target skill (e.g., "AWS")
        transfer_weight: How much experience transfers (0-1)
        rationale: Explanation for the transfer weight
    """

    from_skill: str = Field(description="Source skill")
    to_skill: str = Field(description="Target skill")
    transfer_weight: float = Field(ge=0.0, le=1.0, description="Transfer coefficient (0-1)")
    rationale: str = Field(description="Why this transfer weight")


# =============================================================================
# Phase 2: Evidence Extraction & Tree Building Models
# =============================================================================


class EvidenceCitation(BaseModel):
    """A piece of evidence supporting a skill level achievement.

    Attributes:
        level: The skill level this evidence supports
        question_asked: The interviewer's question that elicited this evidence
        candidate_response: The candidate's full response
        relevant_excerpt: The specific excerpt supporting the level
        confidence: How confident we are in this evidence (0-1)
        extracted_at: When this evidence was extracted
    """

    level: int = Field(ge=1, le=5, description="Skill level this supports")
    question_asked: str = Field(description="Question that elicited this evidence")
    candidate_response: str = Field(description="Full candidate response")
    relevant_excerpt: str = Field(description="Specific supporting excerpt")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence in evidence")
    extracted_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class EvidenceExtraction(BaseModel):
    """Result of extracting evidence from a Q&A exchange.

    Attributes:
        skill_name: Which skill this evidence applies to
        level: Which level is being evaluated
        answer: Yes/No/Insufficient
        evidence: Exact quote from candidate (or N/A)
        confidence: Confidence in this extraction
        reasoning: One-sentence explanation
    """

    skill_name: str = Field(description="Skill being evaluated")
    level: int = Field(ge=1, le=5, description="Level being evaluated")
    answer: Literal["Yes", "No", "Insufficient"] = Field(description="Binary answer")
    evidence: str = Field(description="Exact quote or 'N/A'")
    confidence: float = Field(ge=0.0, le=1.0, description="Extraction confidence")
    reasoning: str = Field(description="One-sentence explanation")


class SkillTreeNode(BaseModel):
    """A node in the candidate's skill tree.

    Tracks the current assessed level and all supporting evidence.

    Attributes:
        skill_name: Name of the skill
        current_level: Highest confirmed level (0 if not assessed)
        max_possible_level: Always 5
        evidence_by_level: Evidence citations organized by level
        last_assessed_at: When this skill was last assessed
    """

    skill_name: str = Field(description="Skill name")
    current_level: int = Field(ge=0, le=5, default=0, description="Highest confirmed level")
    max_possible_level: int = Field(default=5, description="Maximum level (always 5)")
    evidence_by_level: dict[int, list[EvidenceCitation]] = Field(
        default_factory=dict, description="Evidence per level"
    )
    last_assessed_at: str | None = Field(default=None, description="Last assessment timestamp")

    @field_validator("evidence_by_level", mode="before")
    @classmethod
    def coerce_keys_to_int(cls, v: Any) -> dict[int, list[EvidenceCitation]]:
        """Coerce string keys to integers after JSON deserialization."""
        if isinstance(v, dict):
            return {int(k): val for k, val in v.items()}
        return v

    def add_evidence(self, citation: EvidenceCitation) -> None:
        """Add evidence for a specific level."""
        level = citation.level
        if level not in self.evidence_by_level:
            self.evidence_by_level[level] = []
        self.evidence_by_level[level].append(citation)
        self.last_assessed_at = datetime.now(timezone.utc).isoformat()

    def get_evidence_count(self, level: int) -> int:
        """Get number of evidence citations for a level."""
        return len(self.evidence_by_level.get(level, []))

    def get_total_evidence(self) -> int:
        """Get total evidence citations across all levels."""
        return sum(len(v) for v in self.evidence_by_level.values())


class CandidateSkillTree(BaseModel):
    """Complete skill tree for a candidate.

    Tracks all skills and their evidence across an interview.

    Attributes:
        candidate_id: Unique candidate identifier
        session_id: Interview session identifier
        role_id: Role being interviewed for
        skills: Dict mapping skill name to SkillTreeNode
        created_at: When this tree was created
        last_updated: Last update timestamp
    """

    candidate_id: str = Field(description="Candidate identifier")
    session_id: str = Field(description="Interview session identifier")
    role_id: str = Field(description="Role identifier")
    skills: dict[str, SkillTreeNode] = Field(default_factory=dict, description="Skill trees")
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    last_updated: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def get_skill(self, skill_name: str) -> SkillTreeNode | None:
        """Get a skill node by name."""
        return self.skills.get(skill_name)

    def get_or_create_skill(self, skill_name: str) -> SkillTreeNode:
        """Get or create a skill node."""
        if skill_name not in self.skills:
            self.skills[skill_name] = SkillTreeNode(skill_name=skill_name)
        return self.skills[skill_name]

    def update_skill_level(self, skill_name: str, level: int, evidence: EvidenceCitation) -> None:
        """Update a skill's level with evidence."""
        node = self.get_or_create_skill(skill_name)
        node.add_evidence(evidence)
        if level > node.current_level:
            node.current_level = level
        self.last_updated = datetime.now(timezone.utc).isoformat()

    def get_assessed_skills(self) -> list[str]:
        """Get list of skills that have been assessed (level > 0)."""
        return [name for name, node in self.skills.items() if node.current_level > 0]

    def get_unassessed_skills(self, all_skills: list[str]) -> list[str]:
        """Get skills that haven't been assessed yet."""
        return [s for s in all_skills if s not in self.skills or self.skills[s].current_level == 0]


# =============================================================================
# Phase 3: Scoring & Elo Models
# =============================================================================


class SkillScore(BaseModel):
    """Score for a single skill with breakdown.

    Attributes:
        skill_name: Name of the skill
        achieved_level: Level achieved (0-5)
        max_level: Maximum possible level (5)
        weight: Weight for this skill in the role
        weighted_contribution: achieved_level * weight
        evidence_count: Number of evidence citations
        transferred_from: If applicable, skill that contributed via transfer
        transfer_contribution: Additional contribution from skill transfer
    """

    skill_name: str = Field(description="Skill name")
    achieved_level: int = Field(ge=0, le=5, description="Achieved level")
    max_level: int = Field(default=5, description="Max level")
    weight: float = Field(ge=0.0, le=1.0, description="Skill weight")
    weighted_contribution: float = Field(description="Level * weight")
    evidence_count: int = Field(default=0, description="Evidence citations")
    transferred_from: str | None = Field(default=None, description="Source skill for transfer")
    transfer_contribution: float = Field(default=0.0, description="Transfer contribution")


class WeightedScore(BaseModel):
    """Complete weighted score for a candidate.

    Attributes:
        candidate_id: Candidate identifier
        session_id: Session identifier
        role_id: Role identifier
        skill_scores: Individual skill scores
        total_weighted_score: Sum of weighted contributions
        max_possible_score: Maximum possible weighted score (5.0)
        percentage: Percentage of max score achieved
        calculated_at: When this score was calculated
    """

    candidate_id: str = Field(description="Candidate identifier")
    session_id: str = Field(description="Session identifier")
    role_id: str = Field(description="Role identifier")
    skill_scores: list[SkillScore] = Field(description="Individual skill scores")
    total_weighted_score: float = Field(description="Total weighted score")
    max_possible_score: float = Field(default=5.0, description="Max possible (5.0)")
    percentage: float = Field(description="Percentage of max achieved")
    calculated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class SkillComparison(BaseModel):
    """Comparison of two candidates on a single skill.

    Attributes:
        skill_name: Skill being compared
        candidate_a_level: Candidate A's level
        candidate_b_level: Candidate B's level
        weight: Skill weight for this role
        winner: Who won this skill comparison
    """

    skill_name: str = Field(description="Skill name")
    candidate_a_level: int = Field(ge=0, le=5, description="Candidate A level")
    candidate_b_level: int = Field(ge=0, le=5, description="Candidate B level")
    weight: float = Field(ge=0.0, le=1.0, description="Skill weight")
    winner: Literal["a", "b", "tie"] = Field(description="Comparison winner")


class ComparisonBreakdown(BaseModel):
    """Full breakdown of a pairwise comparison.

    Attributes:
        skill_comparisons: Comparison results per skill
        total_a: Candidate A's total weighted score
        total_b: Candidate B's total weighted score
        winner: Overall winner
    """

    skill_comparisons: list[SkillComparison] = Field(description="Per-skill results")
    total_a: float = Field(description="Candidate A total")
    total_b: float = Field(description="Candidate B total")
    winner: Literal["a", "b", "tie"] = Field(description="Overall winner")


class EloMatch(BaseModel):
    """Record of an Elo match between two candidates.

    Attributes:
        match_id: Unique match identifier
        candidate_a_id: First candidate
        candidate_b_id: Second candidate
        winner_id: Winner candidate ID (or None for tie)
        rating_change_a: Rating change for candidate A
        rating_change_b: Rating change for candidate B
        breakdown: Detailed comparison breakdown
        matched_at: When this match occurred
    """

    match_id: str = Field(description="Match identifier")
    candidate_a_id: str = Field(description="Candidate A ID")
    candidate_b_id: str = Field(description="Candidate B ID")
    winner_id: str | None = Field(description="Winner ID or None for tie")
    rating_change_a: float = Field(description="Rating change for A")
    rating_change_b: float = Field(description="Rating change for B")
    breakdown: ComparisonBreakdown = Field(description="Comparison details")
    matched_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class EloRating(BaseModel):
    """Elo rating for a candidate in a specific role.

    Attributes:
        candidate_id: Candidate identifier
        role_id: Role this rating applies to
        rating: Current Elo rating (starts at 1500)
        matches_played: Number of comparisons
        wins: Number of wins
        losses: Number of losses
        ties: Number of ties
        match_history: List of match records
        last_updated: Last update timestamp
    """

    candidate_id: str = Field(description="Candidate identifier")
    role_id: str = Field(description="Role identifier")
    rating: float = Field(default=1500.0, description="Current Elo rating")
    matches_played: int = Field(default=0, description="Total matches")
    wins: int = Field(default=0, description="Wins")
    losses: int = Field(default=0, description="Losses")
    ties: int = Field(default=0, description="Ties")
    match_history: list[str] = Field(default_factory=list, description="Match IDs")
    last_updated: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


# =============================================================================
# Q&A Exchange Model
# =============================================================================


class QAExchange(BaseModel):
    """A single question-answer exchange in the interview.

    Attributes:
        turn_number: Turn number in the interview
        interviewer_question: The question asked
        candidate_response: The candidate's answer
        timestamp: When this exchange occurred
    """

    turn_number: int = Field(description="Turn number")
    interviewer_question: str = Field(description="Question asked")
    candidate_response: str = Field(description="Candidate's answer")
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


# =============================================================================
# Next Question Decision Model
# =============================================================================


class NextQuestionDecision(BaseModel):
    """Decision about what question to ask next.

    Attributes:
        target_skill: Skill to probe
        target_level: Level to probe for
        suggested_question: Generated question
        reasoning: Why this skill/level was chosen
        exploration_value: Score for unexplored potential
    """

    target_skill: str = Field(description="Skill to probe")
    target_level: int = Field(ge=1, le=5, description="Level to probe")
    suggested_question: str = Field(description="Question to ask")
    reasoning: str = Field(description="Why this was chosen")
    exploration_value: float = Field(description="Exploration priority score")
