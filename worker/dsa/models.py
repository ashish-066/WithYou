"""DSA Interview Round — Pydantic data models.

All schemas for:
- Problem packets (examiner-authored ground truth)
- Solution landscape (optimal, alternative, suboptimal, incorrect)
- DSA interview state (nested into InterviewState.dsa_state)
- Interviewer action enum
- Code execution results
- Evidence citations
- Rubric + scoring
- Final DSA report

These models follow the same Pydantic BaseModel convention used in
worker/scoring/models.py. TypedDicts are reserved for LangGraph state;
Pydantic models are used for data validation and Redis serialization.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field

# =============================================================================
# Enums / Literals
# =============================================================================

DSADifficulty = Literal["easy", "medium", "hard"]

SolutionClass = Literal["optimal", "acceptable_alternative", "suboptimal_valid", "incorrect"]

InterviewerAction = Literal[
    "ASK_CLARIFICATION",
    "ASK_WHY",
    "ASK_COMPLEXITY",
    "ASK_EDGE_CASE",
    "ASK_EXAMPLE",
    "ASK_DRY_RUN",
    "CHALLENGE_ASSUMPTION",
    "ASK_ALTERNATIVE",
    "REQUEST_CODE",
    "DISCUSS_FAILURE",
    "ASK_OPTIMIZATION",
    "PROVIDE_HINT",
    "MOVE_FORWARD",
    "END_INTERVIEW",
]

EvidenceVerdict = Literal["Yes", "No", "Insufficient"]


# =============================================================================
# Test Cases
# =============================================================================


class TestCase(BaseModel):
    """A single test case for DSA code execution.

    Attributes:
        input: Python expression or JSON string that will be passed as stdin
        expected_output: Expected stdout output (stripped)
        is_hidden: If True, not revealed to candidate
        description: Optional label (e.g. 'empty array', 'large input')
    """

    input: str = Field(description="Input to pass to the candidate's code (stdin)")
    expected_output: str = Field(description="Expected stdout output (stripped)")
    is_hidden: bool = Field(default=False, description="Whether to reveal to candidate")
    description: str = Field(default="", description="Human-readable label for the test case")


# =============================================================================
# Solution Landscape
# =============================================================================


class ReferenceSolution(BaseModel):
    """The optimal / reference solution authored by the examiner.

    This is NEVER sent to the candidate.
    """

    algorithm: str = Field(description="Algorithm name, e.g. 'hash_map', 'two_pointers'")
    time_complexity: str = Field(description="e.g. 'O(n)'")
    space_complexity: str = Field(description="e.g. 'O(n)'")
    code: str = Field(description="Reference Python code (not shown to candidate)")
    explanation: str = Field(default="", description="Brief explanation for the examiner")


class AlternativeSolution(BaseModel):
    """A valid alternative approach that is not the primary optimal solution.

    Example: Sort + two-pointer for Two Sum (valid but O(n log n) vs O(n)).
    """

    algorithm: str
    time_complexity: str
    space_complexity: str
    description: str = Field(description="Why this is an acceptable alternative")


class SuboptimalSolution(BaseModel):
    """A valid but suboptimal approach.

    Example: Nested loops O(n²) for Two Sum — correct but inefficient.
    A candidate using this should NOT automatically fail.
    """

    algorithm: str
    time_complexity: str
    space_complexity: str
    optimality_gap: str = Field(
        description="Description of the gap vs optimal, e.g. 'O(n²) vs O(n) optimal'"
    )
    is_acceptable_for_passing: bool = Field(
        default=True,
        description="Whether reaching this solution alone can be a passing outcome",
    )


# =============================================================================
# Hint Policy
# =============================================================================


class HintPolicy(BaseModel):
    """Configures how hints are dispensed during the interview."""

    allowed: bool = Field(default=True, description="Whether hints are allowed at all")
    max_hints: int = Field(default=3, description="Maximum hints that can be given")
    progressive: bool = Field(
        default=True,
        description="If True, hints escalate from vague to specific",
    )
    hints: list[str] = Field(
        default_factory=list,
        description="Ordered list of hints from most vague to most specific",
    )
    hint_score_penalty: float = Field(
        default=0.1,
        ge=0.0,
        le=1.0,
        description="Score deduction per hint used (e.g. 0.1 = 10% penalty per hint)",
    )


# =============================================================================
# Scoring Rubric
# =============================================================================


class RubricDimension(BaseModel):
    """One dimension of the DSA scoring rubric."""

    name: str
    weight: float = Field(ge=0.0, le=1.0, description="Fraction of total score (must sum to 1.0)")
    description: str = Field(default="")


class ScoringRubric(BaseModel):
    """Examiner-configurable scoring rubric.

    Default weights match the specification:
        problem_understanding:  10%
        algorithm_selection:    20%
        reasoning:              20%
        code_correctness:       20%
        complexity_analysis:    10%
        edge_case_handling:     10%
        optimization:            5%
        communication:           5%
    """

    dimensions: list[RubricDimension] = Field(
        default_factory=lambda: [
            RubricDimension(name="problem_understanding", weight=0.10),
            RubricDimension(name="algorithm_selection", weight=0.20),
            RubricDimension(name="reasoning", weight=0.20),
            RubricDimension(name="code_correctness", weight=0.20),
            RubricDimension(name="complexity_analysis", weight=0.10),
            RubricDimension(name="edge_case_handling", weight=0.10),
            RubricDimension(name="optimization", weight=0.05),
            RubricDimension(name="communication", weight=0.05),
        ]
    )

    def validate_weights(self) -> bool:
        """Ensure weights sum to approximately 1.0."""
        total = sum(d.weight for d in self.dimensions)
        return 0.95 <= total <= 1.05

    def get_weight(self, dimension_name: str) -> float:
        for d in self.dimensions:
            if d.name == dimension_name:
                return d.weight
        return 0.0


# =============================================================================
# DSA Problem Packet
# =============================================================================


class DSAProblem(BaseModel):
    """Examiner-authored DSA problem packet.

    This is the fixed ground truth. It is stored in Redis and NEVER
    sent to the candidate in full (reference_solution, hidden tests,
    and scoring_rubric are server-side only).
    """

    problem_id: str = Field(description="Unique identifier, e.g. 'two_sum_001'")
    title: str = Field(description="e.g. 'Two Sum'")
    statement: str = Field(description="Full problem statement shown to candidate")
    constraints: list[str] = Field(
        default_factory=list,
        description="e.g. ['2 <= nums.length <= 10^4', '-10^9 <= nums[i] <= 10^9']",
    )
    difficulty: DSADifficulty = Field(default="medium")
    tags: list[str] = Field(
        default_factory=list, description="e.g. ['array', 'hash_table']"
    )

    # --- Ground truth (NEVER sent to candidate) ---
    reference_solution: ReferenceSolution
    acceptable_alternatives: list[AlternativeSolution] = Field(default_factory=list)
    suboptimal_valid: list[SuboptimalSolution] = Field(default_factory=list)

    expected_concepts: list[str] = Field(
        default_factory=list,
        description="Concepts the candidate is expected to demonstrate",
    )
    important_edge_cases: list[str] = Field(
        default_factory=list,
        description="Edge cases the interviewer should probe",
    )
    follow_up_questions: list[str] = Field(
        default_factory=list,
        description="Optional follow-up questions after the main problem",
    )
    optimization_prompts: list[str] = Field(
        default_factory=list,
        description="Phrases Presence can use to prompt optimization",
    )
    interview_objectives: list[str] = Field(
        default_factory=list,
        description="What a successful interview should demonstrate",
    )

    # --- Test cases ---
    public_test_cases: list[TestCase] = Field(
        default_factory=list,
        description="Shown to candidate in problem statement",
    )
    hidden_test_cases: list[TestCase] = Field(
        default_factory=list,
        description="Not revealed; run during/after code submission",
    )
    stress_test_cases: list[TestCase] = Field(
        default_factory=list,
        description="Large inputs to test efficiency",
    )

    # --- Interview configuration ---
    hint_policy: HintPolicy = Field(default_factory=HintPolicy)
    scoring_rubric: ScoringRubric = Field(default_factory=ScoringRubric)

    # --- Metadata ---
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    created_by: str = Field(default="admin")


class DSAProblemPublic(BaseModel):
    """Candidate-safe view of a DSA problem.

    Strips: reference_solution, acceptable_alternatives details, suboptimal_valid,
    hidden_test_cases, stress_test_cases, scoring_rubric, interview_objectives,
    expected_concepts, follow_up_questions, optimization_prompts.
    """

    problem_id: str
    title: str
    statement: str
    constraints: list[str]
    difficulty: DSADifficulty
    tags: list[str]
    public_test_cases: list[TestCase]


# =============================================================================
# Code Execution Models
# =============================================================================


class TestCaseResult(BaseModel):
    """Result of running a single test case."""

    test_index: int
    description: str = ""
    passed: bool
    input: str
    expected_output: str
    actual_output: str
    error: str = ""
    runtime_ms: float = 0.0


class ExecutionResult(BaseModel):
    """Result of executing candidate code against all test cases.

    This is the authoritative source of truth for code correctness.
    The LLM must NEVER contradict or override this.
    """

    success: bool = Field(description="True if code ran without crash/timeout")
    compilation_error: str = Field(default="", description="Syntax/import errors")
    runtime_error: str = Field(default="", description="Runtime exceptions")
    timed_out: bool = Field(default=False)
    timeout_seconds: float = Field(default=5.0)

    test_results: list[TestCaseResult] = Field(default_factory=list)
    tests_passed: int = 0
    tests_total: int = 0
    pass_rate: float = 0.0  # 0.0–1.0

    total_runtime_ms: float = 0.0
    peak_memory_mb: float = 0.0

    # True when the code runner itself failed (e.g. Docker down), not the code
    sandbox_unavailable: bool = False

    code_version: int = Field(default=1, description="Monotonic version number")
    executed_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


# =============================================================================
# Evidence Citations (following existing constrained LLM pattern)
# =============================================================================


class DSAEvidenceCitation(BaseModel):
    """Evidence extracted from a candidate turn for a specific DSA dimension.

    Follows the same constrained LLM pattern as scoring/evidence_extractor.py:
    Yes / No / Insufficient + verbatim quote + confidence + one-sentence reasoning.
    """

    dimension: str = Field(
        description="Rubric dimension, e.g. 'complexity_analysis'"
    )
    criterion: str = Field(
        description="Specific criterion being evaluated, e.g. 'Correctly identified O(n) time complexity'"
    )
    verdict: EvidenceVerdict
    evidence: str = Field(
        description="Exact verbatim quote from candidate transcript, or 'N/A'"
    )
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str = Field(description="One-sentence reasoning for the verdict")
    turn_number: int
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


# =============================================================================
# Mistake / Recovery Tracking
# =============================================================================


class MistakeRecord(BaseModel):
    """Tracks a candidate mistake and whether it was corrected."""

    turn_number: int
    description: str = Field(description="What the mistake was")
    mistake_type: Literal[
        "wrong_algorithm",
        "wrong_complexity",
        "wrong_edge_case",
        "wrong_assumption",
        "bug_in_code",
        "other",
    ]
    corrected: bool = Field(default=False)
    correction_turn: int | None = Field(
        default=None, description="Turn number where correction happened"
    )
    correction_how: Literal[
        "self_corrected",
        "after_light_probe",
        "after_strong_hint",
        "not_corrected",
    ] = Field(default="not_corrected")


# =============================================================================
# DSA Interview State (nested TypedDict for InterviewState)
# =============================================================================

from typing_extensions import TypedDict


class DSARubricScores(TypedDict, total=False):
    """Running rubric scores, updated as evidence is gathered. Range 0.0–1.0."""

    problem_understanding: float
    algorithm_selection: float
    reasoning: float
    code_correctness: float
    complexity_analysis: float
    edge_case_handling: float
    optimization: float
    communication: float


class DSACodeVersion(TypedDict):
    """A snapshot of candidate code at a point in time."""

    version: int
    code: str
    language: str
    timestamp: str
    execution_result: dict[str, Any] | None  # ExecutionResult.model_dump() or None


class DSAHintRecord(TypedDict):
    """Record of a hint being given."""

    hint_index: int
    hint_text: str
    turn_number: int
    timestamp: str
    candidate_response_turn: int | None  # Turn where candidate responded


class DSAInterviewState(TypedDict, total=False):
    """DSA-specific interview state, nested inside InterviewState.dsa_state.

    This is None for Round 1 interviews and has zero impact on existing logic.
    Only populated when interview_mode == 'round2_dsa'.

    Follows the same TypedDict(total=False) convention as InterviewState
    so partial updates work correctly with LangGraph state merging.
    """

    # --- Problem context ---
    problem_id: str
    problem_title: str
    difficulty: str  # DSADifficulty

    # --- Candidate approach tracking ---
    current_approach: str | None       # Narrative: what algo they're proposing
    proposed_algorithm: str | None     # Classified name: "nested_loops", "hash_map", etc.
    candidate_complexity_claim: str | None  # What candidate said the complexity is
    actual_complexity: str | None      # Computed from solution class

    # --- Concept tracking ---
    demonstrated_concepts: list[str]   # Concepts with evidence
    missing_concepts: list[str]        # Required concepts not yet demonstrated

    # --- Mistakes and recovery ---
    mistakes: list[dict[str, Any]]     # List of MistakeRecord.model_dump()

    # --- Optimization tracking ---
    optimization_attempts: int
    reached_optimal: bool
    optimization_trigger: str | None   # "self" | "after_probe" | "after_hint" | None

    # --- Code state ---
    current_code: str | None
    code_language: str                 # "python" for MVP
    code_versions: list[DSACodeVersion]
    last_execution_result: dict[str, Any] | None  # ExecutionResult.model_dump() or None

    # --- Solution classification ---
    matched_solution_class: str | None  # SolutionClass
    optimality_gap: str | None

    # --- Interview flow control ---
    current_objective: str | None      # What Presence is currently trying to assess
    last_action: str | None            # InterviewerAction
    pending_follow_up: str | None      # Next question Presence has prepared
    probing_depth: int                 # How many follow-ups on current topic

    # --- Hints ---
    hints_used: int
    hint_history: list[DSAHintRecord]

    # --- Evidence ---
    evidence_citations: list[dict[str, Any]]  # List of DSAEvidenceCitation.model_dump()

    # --- Running rubric scores (updated incrementally) ---
    scores: DSARubricScores

    # --- Turn counter ---
    dsa_turn_count: int


# =============================================================================
# Final DSA Report
# =============================================================================


class DSAFinalReport(BaseModel):
    """Complete evidence-backed DSA interview report.

    Generated at the end of a Round 2 DSA interview.
    Every major score has linked evidence.
    """

    session_id: str
    problem_id: str
    problem_title: str
    difficulty: DSADifficulty
    generated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    # --- Candidate journey ---
    initial_approach: str
    final_approach: str
    algorithm_classification: SolutionClass
    optimality_gap: str | None

    # --- Code execution (authoritative) ---
    code_submitted: bool
    final_code: str | None
    tests_passed: int
    tests_total: int
    pass_rate: float
    runtime_ms: float
    compilation_error: str | None
    runtime_error: str | None

    # --- Complexity ---
    candidate_time_complexity: str | None
    candidate_space_complexity: str | None
    reference_time_complexity: str
    reference_space_complexity: str

    # --- Behavioral ---
    mistakes: list[dict[str, Any]]  # List of MistakeRecord.model_dump()
    recovery_summary: str
    hints_used: int
    optimization_behavior: str  # Narrative description

    # --- Scores (0.0–1.0 per dimension) ---
    dimension_scores: dict[str, float]
    final_weighted_score: float  # 0.0–1.0
    final_score_percentage: float  # 0–100

    # --- Evidence ---
    evidence_citations: list[dict[str, Any]]

    # --- Elo ---
    elo_rating: float | None
    elo_percentile: float | None

    # --- Summary ---
    strengths: list[str]
    weaknesses: list[str]
    recommendation: Literal["strong_yes", "yes", "maybe", "no", "strong_no"]
    narrative_summary: str
