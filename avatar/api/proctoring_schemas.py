"""Pydantic schemas for anti-cheating/proctoring API endpoints.

Defines request/response models for submitting proctoring events
from the client-side detection system.
"""

from typing import Literal

from pydantic import BaseModel, Field

# =============================================================================
# Cheat Flag Types
# =============================================================================

CheatFlagType = Literal[
    "multiple_faces",  # More than one person detected in frame
    "no_face",  # Candidate face not visible
    "phone_detected",  # Mobile phone visible in frame
    "earphone_detected",  # Earphone/earbud detected
    "tab_switch",  # Candidate switched browser tab/window
    "screen_share",  # Screen sharing detected
    "voice_change",  # Different voice detected
    "copy_paste",  # Copy-paste behavior detected
    "ai_assistance",  # AI-generated response suspected
    "suspicious_timing",  # Unusually fast/slow response
    "blocked_app",  # Desktop app: a blocked app was open during the interview
    "second_screen",  # Desktop app: an extra screen was connected
    "app_closed",  # Desktop app: closed or crashed before the interview was submitted
    "exit_attempt",  # Desktop app: candidate tried to close it
    "emergency_exit",  # Desktop app: candidate used the emergency exit
    "lock_expired",  # Desktop app: unlocked itself at its time limit
    "browser_mode",  # Interview taken in a browser, without the locked app
]

SeverityLevel = Literal["low", "medium", "high", "critical"]


# =============================================================================
# Request Schemas
# =============================================================================


class CheatFlagRequest(BaseModel):
    """Request to report a detected cheating indicator.

    Sent from client-side proctoring system (JavaScript/WebRTC).
    """

    session_id: str = Field(..., max_length=120, description="Interview session ID")
    flag_type: CheatFlagType = Field(..., description="Type of cheating detected")
    severity: SeverityLevel = Field(..., description="Severity level of the violation")
    confidence: float = Field(
        ..., ge=0.0, le=1.0, description="Detection confidence (0-1)"
    )
    description: str = Field(
        ..., max_length=1000, description="Human-readable description of the event"
    )
    evidence: str | None = Field(
        default=None,
        max_length=4000,
        description="Optional evidence (e.g., frame hash, detection metadata)",
    )
    client_timestamp: str | None = Field(
        default=None, max_length=64, description="Client-side timestamp (ISO 8601)"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "session_id": "session-abc123",
                    "flag_type": "multiple_faces",
                    "severity": "high",
                    "confidence": 0.92,
                    "description": "2 faces detected in camera frame",
                    "evidence": "frame_hash:abc123def456",
                    "client_timestamp": "2025-02-01T10:30:00Z",
                }
            ]
        }
    }


class BatchCheatFlagRequest(BaseModel):
    """Request to report multiple cheating indicators at once.

    Useful for batching detections to reduce network overhead.
    """

    session_id: str = Field(..., max_length=120, description="Interview session ID")
    flags: list[CheatFlagRequest] = Field(
        ..., min_length=1, max_length=50, description="List of cheat flags to report"
    )


# =============================================================================
# Response Schemas
# =============================================================================


class CheatFlagResponse(BaseModel):
    """Response after a cheat flag is recorded."""

    flag_id: str = Field(..., description="Unique ID assigned to the flag")
    session_id: str = Field(..., description="Interview session ID")
    flag_type: CheatFlagType = Field(..., description="Type of cheating detected")
    severity: SeverityLevel = Field(..., description="Severity level")
    recorded_at: str = Field(..., description="Server timestamp when recorded")
    integrity_score: float = Field(
        ..., ge=0.0, le=1.0, description="Updated integrity score for the session"
    )


class BatchCheatFlagResponse(BaseModel):
    """Response after recording multiple cheat flags."""

    session_id: str
    flags_recorded: int = Field(
        ..., description="Number of flags successfully recorded"
    )
    flag_ids: list[str] = Field(..., description="IDs of recorded flags")
    integrity_score: float = Field(
        ..., ge=0.0, le=1.0, description="Updated integrity score"
    )


class IntegrityStatusResponse(BaseModel):
    """Response with current integrity status for a session."""

    session_id: str
    integrity_score: float = Field(
        ..., ge=0.0, le=1.0, description="Current integrity score (0-1)"
    )
    total_flags: int = Field(..., description="Total number of flags recorded")
    flags_by_type: dict[str, int] = Field(
        default_factory=dict, description="Count of flags by type"
    )
    flags_by_severity: dict[str, int] = Field(
        default_factory=dict, description="Count of flags by severity"
    )
    recommendation: Literal["proceed", "review", "flag", "reject"] | None = Field(
        default=None, description="Current integrity recommendation"
    )


class IntegrityReportResponse(BaseModel):
    """Full integrity report for a completed interview."""

    session_id: str
    integrity_score: float
    total_flags: int
    flags_by_type: dict[str, int]
    flags_by_severity: dict[str, int]
    critical_incidents: list[dict] = Field(
        default_factory=list, description="High/critical severity flags"
    )
    timeline: list[dict] = Field(
        default_factory=list, description="All flags in chronological order"
    )
    recommendation: Literal["proceed", "review", "flag", "reject"]
    summary: str = Field(..., description="AI-generated summary of integrity concerns")


# =============================================================================
# SSE Event Schemas
# =============================================================================


class CheatDetectedEvent(BaseModel):
    """SSE event when a cheat flag is detected."""

    type: Literal["cheat_detected"] = "cheat_detected"
    session_id: str
    flag_id: str
    flag_type: CheatFlagType
    severity: SeverityLevel
    confidence: float
    description: str
    turn_number: int
    timestamp: str


class IntegrityUpdateEvent(BaseModel):
    """SSE event when integrity score changes."""

    type: Literal["integrity_update"] = "integrity_update"
    session_id: str
    integrity_score: float
    total_flags: int
    recommendation: Literal["proceed", "review", "flag", "reject"] | None
