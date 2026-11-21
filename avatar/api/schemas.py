"""Pydantic models for API request/response schemas."""

from typing import Literal

from pydantic import BaseModel, Field


class CreateCallRequest(BaseModel):
    """Request to create a new video interview call.

    Candidates start with `invite_token` (role, round and problem come from the
    invite and override anything sent here). Signed-in recruiters may start a
    call without an invite, e.g. to try an interview themselves.
    """

    invite_token: str | None = Field(
        default=None,
        max_length=2048,
        description="Signed invite link token for candidates",
    )
    candidate_name: str = Field(
        default="Candidate",
        min_length=1,
        max_length=120,
        description="Display name for the candidate in the call",
    )
    role_id: str | None = Field(
        default=None,
        max_length=120,
        description="Job role ID to fetch job description and title from admin roles",
    )
    linkedin_url: str | None = Field(
        default=None,
        max_length=500,
        description="LinkedIn profile URL for the candidate",
    )
    github_url: str | None = Field(
        default=None,
        max_length=500,
        description="GitHub profile URL for the candidate",
    )
    resume_text: str | None = Field(
        default=None,
        max_length=100_000,
        description="Extracted text from the candidate's resume",
    )
    # --- Round selection ---
    interview_mode: Literal["round1", "round2_dsa"] = Field(
        default="round1",
        description="Interview mode: 'round1' (technical screen) or 'round2_dsa' (coding round)",
    )
    dsa_problem_id: str | None = Field(
        default=None,
        max_length=120,
        description="DSA problem ID for Round 2 interviews. Required when interview_mode='round2_dsa'.",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "candidate_name": "John Doe",
                    "role_id": "senior-swe-backend",
                    "linkedin_url": "https://linkedin.com/in/johndoe",
                    "github_url": "https://github.com/johndoe",
                    "resume_text": "John Doe - Software Engineer...",
                    "interview_mode": "round1",
                },
                {
                    "candidate_name": "Jane Smith",
                    "interview_mode": "round2_dsa",
                    "dsa_problem_id": "two_sum_001",
                },
            ]
        }
    }


class CallResponse(BaseModel):
    """Response with call connection details."""

    call_id: str = Field(..., description="Unique call identifier")
    session_id: str = Field(..., description="Interview session ID")
    room_name: str = Field(..., description="LiveKit room name")
    livekit_url: str = Field(..., description="LiveKit server WebSocket URL")
    livekit_token: str = Field(..., description="JWT token to join the room")
    status: str = Field(default="created", description="Call status")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "call_id": "call-abc123",
                    "session_id": "session-xyz789",
                    "room_name": "interview-session-xyz789",
                    "livekit_url": "wss://your-project.livekit.cloud",
                    "livekit_token": "eyJ...",
                    "status": "created",
                }
            ]
        }
    }


class CallStatusResponse(BaseModel):
    """Response with call status information."""

    call_id: str
    session_id: str
    status: str
    participant_count: int = 0
    created_at: str | None = None


class EndCallResponse(BaseModel):
    """Response after ending a call."""

    call_id: str
    status: str = "ended"
    message: str = "Call ended successfully"
