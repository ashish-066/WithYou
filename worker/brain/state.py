"""Interview state definition for LangGraph with Dual-Brain Architecture.

This module defines the TypedDict that represents the state passed through
the LangGraph interview agent. State is persisted to Redis between invocations.

Extended for dual-brain (fast/slow) architecture with DFA-based routing.
"""

from typing import Any, Literal

from typing_extensions import TypedDict

# to avoid circular imports during startup.
# It is stored as a plain dict in InterviewState and validated on use.

# =============================================================================
# Message Types
# =============================================================================


class Message(TypedDict):
    """A single message in the conversation."""

    role: Literal["system", "assistant", "user"]
    content: str
    timestamp: str  # ISO 8601 format


class MessageSummary(TypedDict):
    """Compressed representation of older messages for token optimization."""

    turn_range: tuple[int, int]  # (start_turn, end_turn)
    key_points: list[str]
    topics_discussed: list[str]
    summary_text: str


# =============================================================================
# Tool Types
# =============================================================================


class ToolCall(TypedDict):
    """A pending or executed tool call."""

    tool_name: str
    tool_type: Literal["fast", "slow"]
    params: dict[str, Any]
    priority: int  # Lower = higher priority


class ToolResult(TypedDict):
    """Result from a tool invocation."""

    tool_name: str
    input: str
    output: Any
    success: bool
    confidence: float  # 0-1
    source: str  # Where data came from
    timestamp: str


# =============================================================================
# Claim Verification Types (for real-time verification engine)
# =============================================================================


class Claim(TypedDict):
    """A verifiable claim extracted from candidate response."""

    id: str
    claim_type: Literal[
        "role", "company", "technology", "duration", "metric", "project", "education"
    ]
    content: str
    source_text: str  # Original transcript excerpt
    timestamp: str


class EvidenceMatch(TypedDict):
    """Evidence found for/against a claim."""

    source: Literal["resume", "github", "linkedin", "live_crawl", "niche_skills"]
    matched_content: str
    relevance_score: float  # 0-1
    match_type: Literal["exact", "partial", "semantic", "none"]


class VerificationResult(TypedDict):
    """Result of verifying a claim against evidence.

    Verdicts:
    - verified: Strong evidence supports the claim (exact match found)
    - unverified: No evidence found or only weak/partial evidence
    - contradiction: Evidence explicitly contradicts the claim
    """

    claim: Claim
    evidence: list[EvidenceMatch]
    verdict: Literal["verified", "unverified", "contradiction"]
    confidence: float  # 0-1
    reasoning: str
    suggested_followup: str | None


# =============================================================================
# Slow Task Types
# =============================================================================


class SlowTask(TypedDict):
    """A task queued for the slow brain."""

    task_id: str
    task_type: Literal[
        "report_descriptive",
        "report_data",
        "deep_analysis",
    ]
    params: dict[str, Any]
    priority: int  # Lower = higher priority
    created_at: str


# =============================================================================
# DFA State Machine Types
# =============================================================================


DFAStateType = Literal[
    "idle",
    "routing",
    "fast_processing",
    "slow_processing",
    "tool_executing",
    "responding",
    "concluding",
]


class DFAState(TypedDict):
    """Deterministic Finite Automaton state for brain routing."""

    current_state: DFAStateType
    previous_state: DFAStateType | None
    transitions: list[str]  # History of state transitions
    transition_count: int


# =============================================================================
# Evaluation Types
# =============================================================================


class RunningScores(TypedDict, total=False):
    """Running evaluation scores updated during interview."""

    technical_depth: float
    problem_solving: float
    communication: float
    experience_fit: float
    cultural_alignment: float


class TimestampNote(TypedDict):
    """A noted moment during the interview."""

    timestamp: str
    tag: Literal[
        "key_insight",
        "concern",
        "strong_answer",
        "weak_answer",
        "claim_made",
        "topic_change",
    ]
    content: str
    turn_number: int
    video_seconds: float | None  # Elapsed seconds from interview start for video sync


# =============================================================================
# Report Types
# =============================================================================


class DescriptiveReport(TypedDict):
    """Narrative interview report."""

    summary: str
    strengths: list[str]
    concerns: list[str]
    recommendation: Literal["strong_yes", "yes", "maybe", "no", "strong_no"]
    detailed_sections: dict[str, str]


class AnalyticsData(TypedDict):
    """Structured data for frontend visualization."""

    rubric_scores: dict[str, float]
    skill_distribution: dict[str, int]
    verification_summary: dict[str, int]  # {"verified": N, "unverified": M, ...}
    timeline: list[dict[str, Any]]
    trust_score: float
    topic_coverage: dict[str, float]  # topic -> coverage percentage


# =============================================================================
# Skill Tree Scoring Types (Evidence-Based Assessment)
# =============================================================================


class SkillTreeState(TypedDict, total=False):
    """State for skill tree scoring during interview.

    Tracks the evidence-based skill assessment that grows as
    the interview progresses.
    """

    # Role requirements (parsed from JD)
    role_id: str
    role_title: str
    skill_weights: dict[str, float]  # skill_name -> weight (0-1)

    # Skill ladders (generated binary questions)
    ladders_generated: bool
    ladder_data: dict[str, Any]  # Serialized skill ladders

    # Skill tree state (candidate's assessed levels)
    tree_initialized: bool
    current_levels: dict[str, int]  # skill_name -> current_level (0-5)
    evidence_counts: dict[str, int]  # skill_name -> evidence count

    # Interview nudging
    recent_skills: list[str]  # Skills discussed in recent turns
    next_suggested_skill: str | None
    next_suggested_level: int | None
    next_suggested_question: str | None

    # Final scoring
    weighted_score: float | None  # 0-1
    score_percentage: float | None  # 0-100
    elo_rating: float | None  # Elo rating if available
    elo_percentile: float | None  # Percentile rank if available


# =============================================================================
# Candidate Profile Types
# =============================================================================


class CandidateProfile(TypedDict, total=False):
    """Pre-crawled candidate data for verification."""

    resume_data: dict[str, Any]
    github_data: dict[str, Any]
    linkedin_data: dict[str, Any]
    niche_skills: dict[str, Any]  # NicheSkillsProfile serialized as dict
    skills_extracted: list[str]
    experience_years: int | None
    crawled_at: str


# =============================================================================
# Main Interview State
# =============================================================================


class InterviewState(TypedDict, total=False):
    """Complete interview state passed through the LangGraph.

    This state is persisted to Redis and loaded on each message.
    The `total=False` allows partial updates.

    Extended for dual-brain architecture with DFA routing.
    """

    # =========================================================================
    # Identifiers
    # =========================================================================
    session_id: str
    candidate_id: str
    template_id: str

    # =========================================================================
    # Job Description (for skill tree scoring)
    # =========================================================================
    job_description: str | None

    # =========================================================================
    # Conversation (with sliding window optimization)
    # =========================================================================
    messages: list[Message]  # Last 10 messages (active window)
    message_summary: MessageSummary | None  # Summarized older messages
    current_input: str  # Latest user input being processed

    # =========================================================================
    # Interview Progress
    # =========================================================================
    current_topic: str
    page_text: str  # a photographed textbook page (study from a page)
    # Language the buddy speaks now: ml-IN | te-IN | en-IN (follows the learner)
    language: str
    # "study" (default) or "talk" (Just talk: emotional buddy, brain/talk.py)
    session_mode: str
    # Talk mode started from a mood chip ("Stressed"): how they said they feel
    mood: str
    # Self-harm language came up this session (brain/talk.py): the end card shows the helpline
    crisis_flagged: bool
    # Understanding map of the current topic (brain/understanding.py)
    understanding: dict[str, Any]
    # This turn answers the buddy's check question (coach it, assess it after the reply)
    answering_check: bool
    # The idea the buddy is asked to check this turn (point id), if any
    check_target: str
    topics_covered: list[str]
    turn_count: int
    max_turns: int  # Configurable interview length

    # =========================================================================
    # Brain Routing (Hybrid: DFA + LLM)
    # =========================================================================
    brain_mode: Literal["fast", "slow", "idle"]
    dfa: DFAState
    input_classification: Literal[
        "conversation",
        "explain_request",
        "quiz_request",
        "report_request",
        "deep_analysis",
        "end_signal",
        "unknown",
    ]

    # Routing metadata (for hybrid LLM router)
    routing_confidence: float  # Confidence of the routing decision (0-1)
    routing_method: Literal["prefilter", "llm", "fallback"]  # How routing was determined
    routing_reasoning: str  # Brief explanation for routing decision (for debugging)
    suggested_tools: list[str]  # Tools suggested by router for the selected brain
    suggested_tool_params: dict[str, dict[str, Any]]  # Parameters for suggested tools

    # =========================================================================
    # Tool Management (Deterministic Queue)
    # =========================================================================
    tool_queue: list[ToolCall]  # Ordered queue of tools to execute
    tool_results: list[ToolResult]  # Results from executed tools
    tool_results_cache: dict[str, Any]  # Cache to avoid re-computation

    # =========================================================================
    # Slow Brain Task Queue
    # =========================================================================
    pending_slow_tasks: list[SlowTask]
    completed_slow_tasks: list[str]  # Task IDs

    # =========================================================================
    # Claim Verification
    # =========================================================================
    pending_claims: list[Claim]
    verified_claims: list[VerificationResult]
    trust_score: float  # Aggregate trust score (0-1)

    # =========================================================================
    # Candidate Profile (Pre-crawled data)
    # =========================================================================
    candidate_urls: dict[str, str | None]  # Input URLs
    candidate_resume_text: str | None  # Raw resume text extracted via OCR
    candidate_linkedin_text: str | None  # LinkedIn "Save to PDF" export text, from the invite
    background_probe: str  # one doubtful claim to probe this turn (brain/candidate_background.py)
    candidate_profile: CandidateProfile | None
    profile_status: Literal["not_started", "in_progress", "completed", "failed"]

    # =========================================================================
    # Evaluation
    # =========================================================================
    running_scores: RunningScores
    timestamp_notes: list[TimestampNote]

    # =========================================================================
    # Report Generation
    # =========================================================================
    report_status: Literal["not_started", "pending", "in_progress", "completed", "failed"]
    descriptive_report: DescriptiveReport | None
    analytics_data: AnalyticsData | None

    # =========================================================================
    # Skill Tree Scoring (Evidence-Based Assessment)
    # =========================================================================
    skill_tree: SkillTreeState | None

    # =========================================================================
    # Interview Control
    # =========================================================================
    interview_ended: bool
    end_reason: str | None  # see interview_flow.EndReason
    # Interview progress (brain/interview_flow.py): phase, unanswered questions,
    # absences, response timings, rating history
    flow: dict[str, Any]
    # One-turn instruction for the interviewer from the system (never from the candidate)
    interviewer_instruction: str

    # =========================================================================
    # Security Events
    # =========================================================================
    security_events: list[dict[str, Any]]

    # =========================================================================
    # Metadata
    # =========================================================================
    started_at: str
    last_updated: str

    # =========================================================================
    # Output - the response to send back
    # =========================================================================
    response: str
    video_url: str | None


# =============================================================================
# State Factory Functions
# =============================================================================


def create_default_dfa_state() -> DFAState:
    """Create initial DFA state."""
    return DFAState(
        current_state="idle",
        previous_state=None,
        transitions=[],
        transition_count=0,
    )


def create_default_interview_state(session_id: str) -> InterviewState:
    """Create a default empty interview state with all fields initialized."""
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).isoformat()

    return InterviewState(
        # Identifiers
        session_id=session_id,
        candidate_id="",
        template_id="",
        # Job Description
        job_description=None,
        # Conversation
        messages=[],
        message_summary=None,
        current_input="",
        # Interview Progress
        current_topic="not chosen yet",
        topics_covered=[],
        turn_count=0,
        max_turns=40,  # safety net; the time budget ends interviews (brain/interview_flow.py)
        # Brain Routing
        brain_mode="idle",
        dfa=create_default_dfa_state(),
        input_classification="unknown",
        routing_confidence=0.0,
        routing_method="prefilter",
        routing_reasoning="",
        suggested_tools=[],
        suggested_tool_params={},
        # Tool Management
        tool_queue=[],
        tool_results=[],
        tool_results_cache={},
        # Slow Tasks
        pending_slow_tasks=[],
        completed_slow_tasks=[],
        # Claim Verification
        pending_claims=[],
        verified_claims=[],
        trust_score=1.0,  # Start with full trust
        # Candidate Profile
        candidate_urls={},
        candidate_resume_text=None,
        candidate_linkedin_text=None,
        background_probe="",
        candidate_profile=None,
        profile_status="not_started",
        # Evaluation
        running_scores={},
        timestamp_notes=[],
        # Report
        report_status="not_started",
        descriptive_report=None,
        analytics_data=None,
        # Skill Tree Scoring
        skill_tree=None,
        # Control
        interview_ended=False,
        end_reason=None,
        flow={},
        interviewer_instruction="",
        # Metadata
        started_at=now,
        last_updated=now,
        # Output
        response="",
        video_url=None,
    )
