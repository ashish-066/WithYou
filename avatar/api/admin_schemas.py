"""Pydantic schemas for admin API endpoints.

Defines request/response models for the dashboard admin API.
"""

from pydantic import BaseModel, Field

# =============================================================================
# Session Schemas
# =============================================================================


class SessionSummary(BaseModel):
    """Summary of an interview session for listing."""

    session_id: str
    candidate_id: str | None = None
    turn_count: int = 0
    max_turns: int = 20
    brain_mode: str = "idle"
    interview_ended: bool = False
    trust_score: float = 1.0
    integrity_score: float = 1.0
    started_at: str | None = None
    last_updated: str | None = None


class SessionListResponse(BaseModel):
    """Response for listing sessions."""

    total_sessions: int
    active_sessions: int
    sessions: list[SessionSummary]


# =============================================================================
# Ops/Metrics Schemas
# =============================================================================


class StreamStats(BaseModel):
    """Statistics for a Redis stream."""

    length: int = 0
    first_entry_id: str | None = None
    last_entry_id: str | None = None
    consumer_groups: int = 0
    pending_messages: int = 0


# =============================================================================
# Demo Schemas
# =============================================================================

# Default job description for demo ELO scoring
DEFAULT_DEMO_JOB_DESCRIPTION = """
Senior Software Engineer

About the Role:
We are looking for a Senior Software Engineer to join our team and help build
scalable, reliable systems. You will work on challenging technical problems
and collaborate with cross-functional teams.

Requirements:
- 5+ years of software engineering experience
- Strong proficiency in Python or Go for backend development
- Experience with cloud platforms (AWS, GCP, or Azure)
- Solid understanding of system design and distributed systems
- Experience with containerization (Docker, Kubernetes)
- Strong communication and collaboration skills
- Experience with CI/CD pipelines and DevOps practices

Nice to Have:
- Experience with microservices architecture
- Familiarity with frontend technologies (React, TypeScript)
- Experience with machine learning or data pipelines
- Leadership or mentoring experience
"""


class DemoConfig(BaseModel):
    """Configuration for scalability demo."""

    session_count: int = Field(default=10, ge=1, le=50)
    enable_avatar: bool = Field(
        default=False, description="Enable BeyondPresence avatars"
    )
    response_delay_ms: int = Field(default=2000, ge=500, le=10000)
    auto_spawn_workers: bool = Field(default=True)
    max_workers: int = Field(default=10, ge=1, le=20)

    # ELO/Skill Tree scoring configuration
    role_id: str = Field(
        default="demo-senior-swe",
        description="Role ID for ELO grouping",
    )
    role_title: str = Field(
        default="Senior Software Engineer",
        description="Human-readable role title",
    )
    job_description: str = Field(
        default=DEFAULT_DEMO_JOB_DESCRIPTION,
        description="Job description for skill extraction and scoring",
    )


class DemoSession(BaseModel):
    """Info about a demo session."""

    session_id: str
    candidate_name: str
    status: str  # pending, active, completed
    turn_count: int = 0
    script_progress: int = 0
    # ELO scoring fields
    elo_rating: float | None = None
    elo_rank: int | None = None
    score_percentage: float | None = None


class DemoLeaderboardEntry(BaseModel):
    """Entry in the demo ELO leaderboard."""

    candidate_id: str
    candidate_name: str
    session_id: str
    elo_rating: float
    score_percentage: float | None = None
    rank: int
    matches_played: int = 0
    wins: int = 0
    losses: int = 0
    ties: int = 0


class DemoStatus(BaseModel):
    """Status of the scalability demo."""

    running: bool = False
    config: DemoConfig | None = None
    sessions: list[DemoSession] = []
    workers_spawned: int = 0
    started_at: str | None = None

    # ELO leaderboard - updated as interviews complete
    elo_leaderboard: list[DemoLeaderboardEntry] = []
    rankings_available: bool = False
    completed_sessions: int = 0
    role_id: str | None = None


# =============================================================================
# Job Role Schemas
# =============================================================================


class JobRoleCreate(BaseModel):
    """Request to create a new job role."""

    role_id: str = Field(
        ...,
        min_length=1,
        max_length=120,
        pattern=r"^[A-Za-z0-9._-]+$",
        description="Unique identifier for the role (e.g., 'senior-swe-backend')",
    )
    role_title: str = Field(
        ..., min_length=1, max_length=200, description="Job title (e.g., 'Senior Software Engineer')"
    )
    job_description: str = Field(
        ...,
        min_length=1,
        max_length=50_000,
        description="Full job description text for skill extraction and scoring",
    )
    is_active: bool = Field(default=True, description="Whether this role is active")


class JobRoleUpdate(BaseModel):
    """Request to update an existing job role."""

    role_title: str | None = Field(default=None, min_length=1, max_length=200, description="Job title")
    job_description: str | None = Field(
        default=None, max_length=50_000, description="Job description text"
    )
    is_active: bool | None = Field(default=None, description="Active status")


class JobRoleResponse(BaseModel):
    """Response for a job role."""

    role_id: str
    role_title: str
    job_description: str
    is_active: bool
    created_at: str
    updated_at: str | None = None


class JobRoleListResponse(BaseModel):
    """Response for listing job roles."""

    total_roles: int
    roles: list[JobRoleResponse]
