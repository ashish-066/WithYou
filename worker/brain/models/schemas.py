"""Pydantic models for tool inputs/outputs with anti-hallucination filtering.

All tools return standardized, filtered outputs to prevent LLM hallucination
and ensure deterministic, verifiable data flow through the graph.
"""

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

# =============================================================================
# Base Output Model (All tools inherit from this)
# =============================================================================


class FilteredToolOutput(BaseModel):
    """Standardized tool output format.

    All tools must return this format to ensure:
    - Source attribution (where data came from)
    - Confidence scoring
    - Success/failure tracking
    - Timestamp for caching
    """

    success: bool
    data: Any
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)
    source: str = Field(description="Origin of data: github, linkedin, tavily, transcript, etc.")
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    error: str | None = None

    @field_validator("data", mode="before")
    @classmethod
    def filter_data(cls, v: Any) -> Any:
        """Strip any potentially hallucinated or unverified data."""
        if isinstance(v, dict):
            # Remove empty or None values
            return {k: val for k, val in v.items() if val is not None and val != ""}
        return v


# =============================================================================
# Fast Brain Tool Outputs
# =============================================================================


class ConversationResponse(BaseModel):
    """Output from the conversation tool (fast brain)."""

    response_text: str = Field(description="The interviewer's response to the candidate")
    follow_up_questions: list[str] = Field(
        default_factory=list,
        max_length=2,
        description="Optional follow-up questions (max 2)",
    )
    topics_touched: list[str] = Field(
        default_factory=list,
        description="Topics mentioned in this exchange",
    )
    claims_detected: list[str] = Field(
        default_factory=list,
        description="Verifiable claims made by candidate (for verification queue)",
    )
    sentiment: Literal["positive", "neutral", "negative", "unclear"] = "neutral"
    confidence: float = Field(ge=0.0, le=1.0, default=0.8)


class SearchResult(BaseModel):
    """A single search result from Tavily."""

    title: str
    url: str
    snippet: str
    relevance_score: float = Field(ge=0.0, le=1.0)


class TavilySearchOutput(BaseModel):
    """Output from Tavily search tool (fast brain)."""

    query: str
    results: list[SearchResult] = Field(
        default_factory=list,
        max_length=3,
        description="Maximum 3 results to minimize token usage",
    )
    total_found: int = 0
    search_time_ms: int = 0

    @field_validator("results", mode="before")
    @classmethod
    def limit_results(cls, v: list) -> list:
        """Enforce maximum of 3 results."""
        if isinstance(v, list):
            return v[:3]
        return v


class TimestampNoteOutput(BaseModel):
    """Output from timestamp noter tool (fast brain)."""

    timestamp: str
    tag: Literal[
        "key_insight",
        "concern",
        "strong_answer",
        "weak_answer",
        "claim_made",
        "topic_change",
    ]
    content: str = Field(max_length=200, description="Brief note about the moment")
    turn_number: int
    created: bool = True


class ToolDecision(BaseModel):
    """Output from tool decider (fast brain).

    Deterministic tool selection based on rules.
    """

    selected_tool: Literal[
        "conversation",
        "tavily_search",
        "timestamp_noter",
        "none",
    ]
    reason: str = Field(max_length=100, description="Brief explanation for selection")
    priority: int = Field(default=1, ge=1, le=10, description="Execution priority (1=highest)")
    params: dict[str, Any] = Field(default_factory=dict)


# =============================================================================
# Slow Brain Tool Outputs
# =============================================================================


class GitHubProfile(BaseModel):
    """Extracted GitHub profile data."""

    username: str
    name: str | None = None
    bio: str | None = None
    public_repos: int = 0
    followers: int = 0
    following: int = 0
    top_languages: list[str] = Field(default_factory=list, max_length=10)
    pinned_repos: list[str] = Field(default_factory=list, max_length=6)
    contribution_count: int | None = None
    profile_url: str
    # Top repositories: name, description, language, stars, pushed_at, fork, url
    repos: list[dict[str, Any]] = Field(default_factory=list)


class LinkedInProfile(BaseModel):
    """Extracted LinkedIn profile data."""

    name: str
    headline: str | None = None
    current_position: str | None = None
    current_company: str | None = None
    location: str | None = None
    experience: list[dict[str, Any]] = Field(default_factory=list)
    education: list[dict[str, Any]] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list, max_length=20)
    profile_url: str


class ResumeExperience(BaseModel):
    """A single work experience entry extracted from resume."""

    company: str = Field(description="Company or organization name")
    title: str | None = Field(default=None, description="Job title or role")
    start_year: int | None = Field(default=None, description="Start year of employment")
    end_year: int | None = Field(
        default=None, description="End year of employment (None if current)"
    )
    team_size: int | None = Field(
        default=None, description="Team size if mentioned (e.g., 'led team of 10')"
    )
    description: str | None = Field(default=None, description="Brief role description")


class ResumeData(BaseModel):
    """Extracted resume data for claim verification.

    This model includes all fields needed for verification logic:
    - skills, experience (companies), certifications for positive matching
    - team_size, experience_years, publications for contradiction detection
    """

    name: str | None = None
    email: str | None = None
    phone: str | None = None

    # Core verification fields
    skills: list[str] = Field(
        default_factory=list,
        description="Technical skills, languages, frameworks, tools",
    )
    experience: list[ResumeExperience] = Field(
        default_factory=list,
        description="Work experience with company names, titles, dates, team sizes",
    )
    education: list[str] = Field(
        default_factory=list,
        description="Education entries (e.g., 'BS Computer Science, Stanford University')",
    )
    certifications: list[str] = Field(
        default_factory=list,
        description="Certifications (e.g., 'AWS Solutions Architect', 'OSCP', 'CKA')",
    )
    projects: list[dict[str, Any]] = Field(default_factory=list)

    # Derived fields for verification
    companies: list[str] = Field(
        default_factory=list,
        description="Flattened list of company names from experience",
    )
    experience_years: int | None = Field(
        default=None,
        description="Total years of professional experience",
    )
    max_team_size: int | None = Field(
        default=None,
        description="Largest team size mentioned across all roles",
    )
    publications: int | None = Field(
        default=None,
        description="Number of publications/papers mentioned",
    )
    education_summary: str | None = Field(
        default=None,
        description="Concatenated education for keyword matching",
    )


# =============================================================================
# Niche Skills Detection Models
# =============================================================================


class NicheSkillItem(BaseModel):
    """A single niche achievement detected from candidate data.

    Represents exceptional achievements like OSS program participation,
    hackathon wins, or notable open source contributions.
    """

    category: Literal["oss_program", "hackathon", "oss_contribution"]
    name: str = Field(description="Achievement name, e.g., 'Google Summer of Code 2023'")
    evidence: str = Field(description="Source: 'GitHub bio', 'Resume', 'GitHub README'")
    confidence: float = Field(ge=0.0, le=1.0, default=0.8)
    url: str | None = None
    year: int | None = None


class NicheSkillsProfile(BaseModel):
    """Collection of niche achievements for a candidate.

    Tracks exceptional achievements that indicate high-potential candidates:
    - OSS programs: GSoC, LFX Mentorship, Outreachy, MLH Fellowship
    - Hackathons: Wins or top placements
    - OSS contributions: Notable org memberships, high-star repos
    """

    programs: list[NicheSkillItem] = Field(
        default_factory=list,
        description="OSS programs: GSoC, LFX, Outreachy, MLH Fellowship",
    )
    hackathons: list[NicheSkillItem] = Field(
        default_factory=list,
        description="Hackathon wins or top placements",
    )
    oss_contributions: list[NicheSkillItem] = Field(
        default_factory=list,
        description="Notable OSS contributions (high-star repos, org memberships)",
    )
    detected_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def get_score_boost(self) -> float:
        """Calculate experience_fit score boost (0.0-1.0 on 5-point scale).

        Returns a boost value to add to experience_fit score:
        - Each OSS program: +0.25
        - Each hackathon achievement: +0.15
        - Each notable OSS contribution: +0.1
        - Maximum total boost: 1.0 (20% on 5-point scale)
        """
        boost = (
            len(self.programs) * 0.25
            + len(self.hackathons) * 0.15
            + len(self.oss_contributions) * 0.1
        )
        return min(boost, 1.0)

    def is_empty(self) -> bool:
        """Check if any achievements were detected."""
        return not (self.programs or self.hackathons or self.oss_contributions)


class ProfileCrawlResult(BaseModel):
    """Output from profile crawler tool (slow brain)."""

    github: GitHubProfile | None = None
    linkedin: LinkedInProfile | None = None
    resume: ResumeData | None = None
    # LinkedIn can't be read automatically; its "Save to PDF" export, parsed like a resume
    linkedin_export: ResumeData | None = None
    # Other links (portfolio, blog, project pages): url, title, text, error
    links: list[dict[str, Any]] = Field(default_factory=list)
    niche_skills: NicheSkillsProfile | None = None
    skills_extracted: list[str] = Field(default_factory=list)
    experience_years: int | None = None
    crawl_timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    errors: list[str] = Field(default_factory=list)


class DescriptiveReportOutput(BaseModel):
    """Output from descriptive report generator (slow brain)."""

    summary: str = Field(description="Executive summary (2-3 paragraphs)")
    strengths: list[str] = Field(default_factory=list, max_length=10)
    concerns: list[str] = Field(default_factory=list, max_length=10)
    recommendation: Literal["strong_yes", "yes", "maybe", "no", "strong_no"]
    recommendation_reasoning: str
    detailed_sections: dict[str, str] = Field(
        default_factory=dict,
        description="Sections like 'Technical Skills', 'Communication', etc.",
    )
    generated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class AnalyticsReportData(BaseModel):
    """Output from analytics report generator (slow brain).

    Structured data for frontend visualization (graphs, charts).
    """

    rubric_scores: dict[str, float] = Field(
        default_factory=dict,
        description="Dimension -> score (0-5 scale)",
    )
    skill_distribution: dict[str, int] = Field(
        default_factory=dict,
        description="Skill -> mention count",
    )
    verification_summary: dict[str, int] = Field(
        default_factory=lambda: {
            "verified": 0,
            "unverified": 0,
            "contradiction": 0,
        },
        description="Verification verdict counts",
    )
    timeline: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Interview progression events",
    )
    trust_score: float = Field(ge=0.0, le=1.0, default=1.0)
    topic_coverage: dict[str, float] = Field(
        default_factory=dict,
        description="Topic -> coverage percentage (0-100)",
    )
    interview_duration_minutes: int | None = None
    total_turns: int = 0
    generated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


# =============================================================================
# Input Models (for tool parameters)
# =============================================================================


class ConversationInput(BaseModel):
    """Input for conversation tool."""

    user_message: str
    context_summary: str | None = None
    current_topic: str = "general"
    interview_phase: Literal["intro", "technical", "behavioral", "closing"] = "technical"


class SearchInput(BaseModel):
    """Input for Tavily search tool."""

    query: str = Field(max_length=200)
    max_results: int = Field(default=3, le=3)


class TimestampNoteInput(BaseModel):
    """Input for timestamp noter tool."""

    tag: Literal[
        "key_insight",
        "concern",
        "strong_answer",
        "weak_answer",
        "claim_made",
        "topic_change",
    ]
    content: str = Field(max_length=200)
    turn_number: int


class ProfileCrawlInput(BaseModel):
    """Input for profile crawler tool."""

    github_url: str | None = None
    linkedin_url: str | None = None
    resume_url: str | None = None


class ReportGenerationInput(BaseModel):
    """Input for report generation tools."""

    include_verification: bool = True
    include_timeline: bool = True
    include_recommendations: bool = True


# =============================================================================
# Routing Models (Hybrid LLM Router)
# =============================================================================


class RoutingDecision(BaseModel):
    """Output from the hybrid router for brain selection.

    Used by both the fast pre-filter and LLM router to communicate routing decisions.
    """

    brain: Literal["fast", "slow", "end"] = Field(
        description="Target brain: fast (conversation), slow (analysis), or end (conclude)"
    )
    confidence: float = Field(
        ge=0.0, le=1.0, default=0.5, description="Confidence in routing decision"
    )
    reasoning: str = Field(
        default="", max_length=200, description="Brief explanation for the routing decision"
    )
    routing_method: Literal["prefilter", "llm", "fallback"] = Field(
        default="prefilter", description="How this decision was made"
    )
    suggested_tools: list[str] = Field(
        default_factory=list,
        description="Tools suggested by router for the selected brain to execute",
    )
    tool_params: dict[str, dict[str, Any]] = Field(
        default_factory=dict,
        description="Parameters for each suggested tool: {tool_name: {param: value}}",
    )
    input_classification: Literal[
        "conversation",
        "question",
        "profile_request",
        "report_request",
        "deep_analysis",
        "search_request",
        "end_signal",
        "unknown",
    ] = Field(default="unknown", description="Classification of the input type")


class PrefilterResult(BaseModel):
    """Result from the fast regex-based pre-filter.

    Used to quickly route obvious cases without LLM calls.
    """

    classification: Literal[
        "conversation",
        "question",
        "profile_request",
        "report_request",
        "deep_analysis",
        "search_request",
        "end_signal",
        "unknown",
    ]
    confidence: float = Field(
        ge=0.0, le=1.0, description="Confidence score - below threshold triggers LLM routing"
    )
    matched_patterns: list[str] = Field(
        default_factory=list, description="Patterns that matched (for debugging)"
    )
    suggested_brain: Literal["fast", "slow", "end"] = "fast"
    suggested_tools: list[str] = Field(default_factory=list)


class LLMRoutingRequest(BaseModel):
    """Input context for the LLM router when pre-filter confidence is low."""

    user_input: str = Field(description="The current user message")
    turn_count: int = Field(default=0, description="Current turn number in interview")
    max_turns: int = Field(default=40, description="Safety cap on turns (the time budget ends interviews)")
    topics_covered: list[str] = Field(default_factory=list)
    current_topic: str = Field(default="general")
    has_candidate_profile: bool = Field(
        default=False, description="Whether candidate profile data is loaded"
    )
    recent_messages: list[dict[str, str]] = Field(
        default_factory=list, description="Last few messages for context"
    )
    pending_claims_count: int = Field(default=0, description="Number of unverified claims")


class ToolRoutingDecision(BaseModel):
    """Detailed tool routing decision for brain execution.

    Returned by LLM router to specify exactly which tools should run and how.
    """

    tools: list[str] = Field(default_factory=list, description="Ordered list of tools to execute")
    tool_params: dict[str, dict[str, Any]] = Field(
        default_factory=dict, description="Parameters for each tool"
    )
    reasoning: str = Field(default="", max_length=200)
    skip_conversation: bool = Field(
        default=False,
        description="If True, tools fully handle request - skip conversation generation",
    )
    priority_order: list[str] = Field(default_factory=list, description="Execution order for tools")
