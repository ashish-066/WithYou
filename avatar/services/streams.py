"""Redis Streams manager for Avatar Service.

Handles publishing transcriptions to interview:requests
and consuming responses from interview:responses.
"""

import asyncio
import json
import logging
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from redis.asyncio import Redis
from redis.exceptions import ResponseError

from core.config import settings

logger = logging.getLogger(__name__)

# Last response stream ID an agent handled per session (so a restarted job resumes there)
LAST_SPOKEN_KEY_PREFIX = "avatar:last_spoken"
LAST_SPOKEN_TTL_SECONDS = 6 * 3600


@dataclass
class StreamMessage:
    """A message from the Redis stream."""

    message_id: str
    stream: str
    session_id: str
    message_type: str
    content: str
    timestamp: str
    raw_data: dict[str, Any]

    @classmethod
    def from_stream_entry(
        cls, stream: str, message_id: str, data: dict[str, str]
    ) -> "StreamMessage":
        return cls(
            message_id=message_id,
            stream=stream,
            session_id=data.get("session_id", ""),
            message_type=data.get("message_type", "unknown"),
            content=data.get("content", ""),
            timestamp=data.get("timestamp", ""),
            raw_data=data,
        )


class AvatarStreamManager:
    """Manages Redis Streams for Avatar Service.

    Publishes transcriptions (simulated STT output) to the request stream
    and consumes AI responses from the response stream.
    """

    def __init__(
        self,
        redis: Redis,
        request_stream: str | None = None,
        response_stream: str | None = None,
        consumer_group: str | None = None,
        consumer_name: str | None = None,
    ):
        self.redis = redis
        self.request_stream = request_stream or settings.request_stream
        self.response_stream = response_stream or settings.response_stream
        self.consumer_group = consumer_group or settings.consumer_group
        self.consumer_name = consumer_name or settings.consumer_name

    async def create_consumer_group(self) -> None:
        """Create consumer group for the response stream if it doesn't exist."""
        try:
            await self.redis.xgroup_create(
                self.response_stream,
                self.consumer_group,
                id="0",  # Start from beginning of stream
                mkstream=True,  # Create stream if doesn't exist
            )
            logger.info(
                f"Created consumer group '{self.consumer_group}' "
                f"on stream '{self.response_stream}'"
            )
        except ResponseError as e:
            if "BUSYGROUP" in str(e):
                logger.debug(f"Consumer group '{self.consumer_group}' already exists")
            else:
                raise

    async def publish_transcription(
        self,
        session_id: str,
        content: str,
        message_type: str = "candidate_response",
        extra_fields: dict[str, Any] | None = None,
    ) -> str:
        """Publish a transcription to the request stream.

        This simulates STT output being sent to the Brain Worker.
        """
        data = {
            "session_id": session_id,
            "message_type": message_type,
            "content": content,
            "timestamp": datetime.now(UTC).isoformat(),
            "source": "avatar",
        }

        if extra_fields:
            # Add extra fields to the message data
            # Redis streams values must be strings, so we serialize dicts if needed
            for key, value in extra_fields.items():
                if isinstance(value, (dict, list)):
                    data[key] = json.dumps(value)
                else:
                    data[key] = str(value)

        message_id = await self.redis.xadd(
            self.request_stream, data, maxlen=settings.stream_maxlen, approximate=True
        )
        logger.debug(f"Published transcription to {self.request_stream}: {message_id}")

        return message_id

    @staticmethod
    def _last_spoken_key(session_id: str) -> str:
        return f"{LAST_SPOKEN_KEY_PREFIX}:{session_id}"

    async def mark_spoken(self, session_id: str, message_id: str) -> None:
        """Remember the last response handled for a session, so a restarted
        agent job doesn't speak it again."""
        try:
            await self.redis.set(
                self._last_spoken_key(session_id), message_id, ex=LAST_SPOKEN_TTL_SECONDS
            )
        except Exception as e:
            logger.warning(f"Failed to record last spoken response for {session_id}: {e}")

    async def response_start_id(self, session_id: str, since_ms: int | None = None) -> str | None:
        """Stream ID a session's listener should read after: the later of
        since_ms (e.g. room creation) and the last response already handled."""
        candidates: list[str] = []
        if since_ms:
            # Exclusive start, so step back 1ms to include entries at since_ms
            candidates.append(f"{since_ms - 1}-0")
        try:
            last_spoken = await self.redis.get(self._last_spoken_key(session_id))
            if last_spoken:
                candidates.append(last_spoken)
        except Exception as e:
            logger.warning(f"Failed to read last spoken response for {session_id}: {e}")

        if not candidates:
            return None

        def parse(stream_id: str) -> tuple[int, int]:
            ms, _, seq = stream_id.partition("-")
            return int(ms), int(seq or 0)

        return max(candidates, key=parse)

    async def consume_responses(
        self,
        session_id: str | None = None,
        count: int | None = None,
        block_ms: int | None = None,
        lookback_ms: int = 120_000,
        start_id: str | None = None,
    ) -> AsyncGenerator[StreamMessage, None]:
        """Consume responses from the response stream.

        Uses plain XREAD (no consumer group) so every listener sees every
        response and keeps only its own session's. A shared consumer group
        would hand each response to exactly one listener, so with concurrent
        interviews a reply could land in another session's listener and be lost.

        Args:
            session_id: Only yield responses for this session (None = all)
            count: Number of messages to read at once
            block_ms: Milliseconds to block waiting for messages
            lookback_ms: If no start_id, start this far back in time, so responses
                published before the listener started (e.g. the DSA intro) aren't missed
            start_id: Read entries after this stream ID (overrides lookback_ms)

        Yields:
            StreamMessage objects from the response stream
        """
        count = count or settings.consume_batch_size
        block_ms = block_ms or settings.consume_block_ms

        if start_id:
            last_id = start_id
        else:
            # Stream IDs are "<ms>-<seq>", so a timestamp works as a start position
            start_ms = int(datetime.now(UTC).timestamp() * 1000) - lookback_ms
            last_id = f"{max(start_ms, 0)}-0"

        while True:
            try:
                result = await self.redis.xread(
                    streams={self.response_stream: last_id},
                    count=count,
                    block=block_ms,
                )

                if not result:
                    # No messages, continue blocking
                    continue

                for stream_name, messages in result:
                    for message_id, data in messages:
                        last_id = message_id
                        if session_id and data.get("session_id") != session_id:
                            continue
                        yield StreamMessage.from_stream_entry(
                            stream=stream_name,
                            message_id=message_id,
                            data=data,
                        )

            except Exception as e:
                logger.error(f"Error consuming from stream: {e}")
                await asyncio.sleep(1)

    async def consume_pending(
        self,
        min_idle_ms: int | None = None,
        count: int = 10,
    ) -> AsyncGenerator[StreamMessage, None]:
        """Consume pending messages that were not ACKed.

        Reclaims messages that have been idle for too long,
        typically from crashed or slow consumers.

        Args:
            min_idle_ms: Minimum idle time before claiming
            count: Maximum messages to claim

        Yields:
            StreamMessage objects that were reclaimed
        """
        min_idle_ms = min_idle_ms or settings.idle_claim_ms

        try:
            # XAUTOCLAIM: claim idle pending messages
            result = await self.redis.xautoclaim(
                name=self.response_stream,
                groupname=self.consumer_group,
                consumername=self.consumer_name,
                min_idle_time=min_idle_ms,
                start_id="0-0",
                count=count,
            )

            if not result or len(result) < 2:
                return

            # Result: (next_start_id, [(message_id, data), ...], deleted_ids)
            _, messages, _ = result

            for message_id, data in messages:
                if data:  # Skip deleted/nil messages
                    yield StreamMessage.from_stream_entry(
                        stream=self.response_stream,
                        message_id=message_id,
                        data=data,
                    )

        except Exception as e:
            logger.error(f"Error claiming pending messages: {e}")

    async def ack(self, message_id: str) -> bool:
        """Acknowledge a message has been processed.

        Removes the message from the pending entries list (PEL).

        Args:
            message_id: The Redis message ID to acknowledge

        Returns:
            True if the message was acknowledged
        """
        result = await self.redis.xack(
            self.response_stream,
            self.consumer_group,
            message_id,
        )
        if result:
            logger.debug(f"Acknowledged message {message_id}")
        return result > 0
