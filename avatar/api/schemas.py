"""Pydantic models for API request/response schemas."""

from typing import Literal

from pydantic import BaseModel, Field


class CreateCallRequest(BaseModel):
    """Request to start a study session (signed-in learner only)."""

    # Starting language; the learner can switch by speaking another one
    language: Literal["ml-IN", "te-IN", "en-IN"] = Field(
        default="ml-IN", description="Language the buddy starts in"
    )

    candidate_name: str = Field(
        default="Learner",
        min_length=1,
        max_length=120,
        description="Display name for the learner in the call",
    )


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
