"""LiveKit room management and token generation service.

Handles creation of LiveKit rooms and generation of access tokens
for participants to join interview sessions.
"""

import logging
from datetime import timedelta

from livekit import api

from core.config import settings

logger = logging.getLogger(__name__)


class LiveKitService:
    """Manages LiveKit rooms and access tokens."""

    def __init__(self):
        """Initialize the LiveKit API client."""
        self._api: api.LiveKitAPI | None = None

    @property
    def api_client(self) -> api.LiveKitAPI:
        """Lazy initialization of LiveKit API client."""
        if self._api is None:
            self._api = api.LiveKitAPI(
                url=settings.livekit_url,
                api_key=settings.livekit_api_key,
                api_secret=settings.livekit_api_secret,
            )
        return self._api

    async def create_room(self, room_name: str) -> api.Room:
        """Create a new LiveKit room for an interview session.

        Args:
            room_name: Unique name for the room (typically interview-{session_id})

        Returns:
            The created Room object
        """
        try:
            room = await self.api_client.room.create_room(
                api.CreateRoomRequest(
                    name=room_name,
                    empty_timeout=300,  # 5 minutes
                    max_participants=3,  # User + Agent + Avatar
                )
            )
            logger.info(f"Created LiveKit room: {room_name}")
            return room
        except Exception as e:
            logger.error(f"Failed to create room {room_name}: {e}")
            raise

    async def dispatch_agent(self, room_name: str) -> None:
        """Send our voice agent (registered as settings.agent_dispatch_name) to the room."""
        await self.api_client.agent_dispatch.create_dispatch(
            api.CreateAgentDispatchRequest(agent_name=settings.agent_dispatch_name, room=room_name)
        )
        logger.info(f"Dispatched agent '{settings.agent_dispatch_name}' to {room_name}")

    async def delete_room(self, room_name: str) -> None:
        """Delete a LiveKit room.

        Args:
            room_name: Name of the room to delete
        """
        try:
            await self.api_client.room.delete_room(
                api.DeleteRoomRequest(room=room_name)
            )
            logger.info(f"Deleted LiveKit room: {room_name}")
        except Exception as e:
            logger.warning(f"Failed to delete room {room_name}: {e}")

    async def list_rooms(self) -> list[api.Room]:
        """List all active interview rooms."""
        response = await self.api_client.room.list_rooms(api.ListRoomsRequest())
        return list(response.rooms)

    async def get_room(self, room_name: str) -> api.Room | None:
        """Get a specific room by name."""
        rooms = await self.list_rooms()
        for room in rooms:
            if room.name == room_name:
                return room
        return None

    def generate_participant_token(
        self,
        room_name: str,
        participant_identity: str,
        participant_name: str | None = None,
        ttl: timedelta | None = None,
    ) -> str:
        """Generate an access token for a participant to join a room.

        Args:
            room_name: Name of the room to join
            participant_identity: Unique identifier for the participant
            participant_name: Display name for the participant
            ttl: Token time-to-live (default: 2 hours; rejoining issues a new one)

        Returns:
            JWT access token string
        """
        if ttl is None:
            ttl = timedelta(hours=2)

        token = api.AccessToken(
            api_key=settings.livekit_api_key,
            api_secret=settings.livekit_api_secret,
        )

        token.with_identity(participant_identity)
        if participant_name:
            token.with_name(participant_name)
        token.with_ttl(ttl)

        # Grant permissions to join the room
        token.with_grants(
            api.VideoGrants(
                room_join=True,
                room=room_name,
                can_publish=True,
                can_subscribe=True,
                can_publish_data=True,
            )
        )

        jwt_token = token.to_jwt()
        logger.debug(f"Generated token for {participant_identity} in room {room_name}")
        return jwt_token

    def generate_agent_token(
        self,
        room_name: str,
        agent_identity: str = "interview-agent",
        agent_name: str | None = None,
    ) -> str:
        """Generate an access token for the interview agent.

        The agent token has special permissions for agent operations.

        Args:
            room_name: Name of the room
            agent_identity: Identity for the agent participant
            agent_name: Display name for the agent

        Returns:
            JWT access token string
        """
        if agent_name is None:
            agent_name = settings.agent_name

        token = api.AccessToken(
            api_key=settings.livekit_api_key,
            api_secret=settings.livekit_api_secret,
        )

        token.with_identity(agent_identity)
        token.with_name(agent_name)
        token.with_ttl(timedelta(hours=24))

        # Agent has full permissions
        token.with_grants(
            api.VideoGrants(
                room_join=True,
                room=room_name,
                can_publish=True,
                can_subscribe=True,
                can_publish_data=True,
                agent=True,  # Mark as agent
            )
        )

        return token.to_jwt()

    async def close(self) -> None:
        """Close the API client."""
        if self._api is not None:
            await self._api.aclose()
            self._api = None


# Global service instance
livekit_service = LiveKitService()
