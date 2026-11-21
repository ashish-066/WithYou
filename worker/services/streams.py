"""Redis Streams manager for pub/sub messaging.

Handles the interview:requests and interview:responses streams
with consumer group support for horizontal scaling.
"""

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, AsyncGenerator

from redis.asyncio import Redis
from redis.exceptions import ResponseError

from core.config import settings

logger = logging.getLogger(__name__)


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
        """Create StreamMessage from raw Redis stream entry."""
        # Support both 'message_type' and 'type' fields for compatibility
        # The slow_task_trigger messages use 'type' field
        message_type = data.get("message_type") or data.get("type", "unknown")
        return cls(
            message_id=message_id,
            stream=stream,
            session_id=data.get("session_id", ""),
            message_type=message_type,
            content=data.get("content", ""),
            timestamp=data.get("timestamp", ""),
            raw_data=data,
        )


class StreamManager:
    """Manages Redis Streams for interview message passing."""

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
        try:
            await self.redis.xgroup_create(
                self.request_stream,
                self.consumer_group,
                id="0",  # Start from beginning of stream
                mkstream=True,  # Create stream if doesn't exist
            )
            logger.info(
                f"Created consumer group '{self.consumer_group}' on stream '{self.request_stream}'"
            )
        except ResponseError as e:
            if "BUSYGROUP" in str(e):
                logger.debug(f"Consumer group '{self.consumer_group}' already exists")
            else:
                raise

    async def consume(
        self,
        count: int = 1,
        block_ms: int = 5000,
    ) -> AsyncGenerator[StreamMessage, None]:
        """Consume messages from the request stream.

        Uses XREADGROUP for consumer group semantics:
        - Each message is delivered to only one consumer
        - Messages must be ACKed after processing
        - Unacked messages can be claimed by other consumers

        Also reclaims idle pending messages every reclaim_interval_seconds, so a
        message whose processing failed (or whose worker died) gets retried
        instead of sitting in the PEL until some worker restarts.
        """
        import asyncio

        loop = asyncio.get_running_loop()
        last_reclaim = loop.time()

        while True:
            if loop.time() - last_reclaim >= settings.reclaim_interval_seconds:
                last_reclaim = loop.time()
                async for message in self.consume_pending(
                    min_idle_ms=settings.reclaim_min_idle_ms
                ):
                    logger.info(f"Reclaimed pending message {message.message_id}")
                    yield message

            try:
                # XREADGROUP: read new messages for this consumer
                # ">" means only new messages not yet delivered to any consumer
                result = await self.redis.xreadgroup(
                    groupname=self.consumer_group,
                    consumername=self.consumer_name,
                    streams={self.request_stream: ">"},
                    count=count,
                    block=block_ms,
                )

                if not result:
                    # No messages (block timeout), continue blocking
                    continue

                for stream_name, messages in result:
                    for message_id, data in messages:
                        yield StreamMessage.from_stream_entry(
                            stream=stream_name,
                            message_id=message_id,
                            data=data,
                        )

            except Exception as e:
                logger.error(f"Error consuming from stream: {e}")
                # Brief pause before retrying
                import asyncio

                await asyncio.sleep(1)

    async def consume_pending(
        self,
        min_idle_ms: int = 30000,
        count: int = 10,
    ) -> AsyncGenerator[StreamMessage, None]:
        """Consume pending messages that were not ACKed."""
        try:
            # XAUTOCLAIM: claim idle pending messages
            result = await self.redis.xautoclaim(
                name=self.request_stream,
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
                        stream=self.request_stream,
                        message_id=message_id,
                        data=data,
                    )

        except Exception as e:
            logger.error(f"Error claiming pending messages: {e}")

    async def ack(self, message_id: str) -> bool:
        """Removes the message from the pending entries list (PEL)."""

        result = await self.redis.xack(
            self.request_stream,
            self.consumer_group,
            message_id,
        )
        if result:
            logger.debug(f"Acknowledged message {message_id}")
        return result > 0

    async def publish_response(
        self,
        session_id: str,
        content: str,
        message_type: str = "avatar_response",
        extra_fields: dict[str, Any] | None = None,
    ) -> str:
        """Publish a response to the response stream."""
        data: dict[str, Any] = {
            "session_id": session_id,
            "message_type": message_type,
            "content": content,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "worker_id": settings.worker_id,
        }

        if extra_fields:
            # Serialize complex fields to JSON
            for key, value in extra_fields.items():
                if isinstance(value, (dict, list)):
                    data[key] = json.dumps(value)
                else:
                    data[key] = str(value)

        message_id = await self.redis.xadd(
            self.response_stream, data, maxlen=settings.stream_maxlen, approximate=True
        )
        logger.debug(f"Published response to {self.response_stream}: {message_id}")

        return message_id

    async def touch(self, message_id: str) -> None:
        """Reset a pending message's idle time while we're still processing it.

        Periodic reclaim takes messages idle longer than reclaim_min_idle_ms, and
        idle time counts from delivery, so a long run (profile crawl, report)
        would otherwise be handed to a second worker mid-processing.
        """
        await self.redis.xclaim(
            self.request_stream,
            self.consumer_group,
            self.consumer_name,
            min_idle_time=0,
            message_ids=[message_id],
            justid=True,
        )

    async def dead_letter(self, message: StreamMessage, error: str, attempts: int) -> str:
        """Keep a message we gave up on, with why, instead of losing it."""
        entry = {
            "original_id": message.message_id,
            "session_id": message.session_id,
            "message_type": message.message_type,
            "error": error[:2000],
            "attempts": str(attempts),
            "dead_at": datetime.now(timezone.utc).isoformat(),
            "worker_id": settings.worker_id,
            "payload": json.dumps(message.raw_data)[:100_000],
        }
        return await self.redis.xadd(
            settings.dead_letter_stream, entry, maxlen=10_000, approximate=True
        )

    async def remove_consumer(self) -> bool:
        """Remove this consumer from the consumer group.

        Called during graceful shutdown to clean up.

        Returns:
            True if consumer was removed successfully
        """
        try:
            # Deleting a consumer discards its pending entries, which would make
            # them unreclaimable. Leave it in the group so another worker retries them.
            pending = await self.redis.xpending_range(
                self.request_stream,
                self.consumer_group,
                min="-",
                max="+",
                count=1,
                consumername=self.consumer_name,
            )
            if pending:
                logger.info(
                    f"Keeping consumer {self.consumer_name}: it has pending messages to reclaim"
                )
                return False

            result = await self.redis.xgroup_delconsumer(
                self.request_stream,
                self.consumer_group,
                self.consumer_name,
            )
            logger.info(f"Removed consumer {self.consumer_name} from group (pending: {result})")
            return True
        except Exception as e:
            logger.warning(f"Failed to remove consumer: {e}")
            return False

    async def get_stream_info(self) -> dict[str, Any]:
        """Get information about the request stream.

        Returns:
            Stream info including length, groups, etc.
        """
        try:
            info = await self.redis.xinfo_stream(self.request_stream)
            return {
                "length": info.get("length", 0),
                "first_entry": info.get("first-entry"),
                "last_entry": info.get("last-entry"),
                "groups": info.get("groups", 0),
            }
        except Exception as e:
            logger.warning(f"Failed to get stream info: {e}")
            return {}

    async def get_consumer_info(self) -> list[dict[str, Any]]:
        """Get information about consumers in this group.

        Returns:
            List of consumer info dicts
        """
        try:
            consumers = await self.redis.xinfo_consumers(
                self.request_stream,
                self.consumer_group,
            )
            return [
                {
                    "name": c.get("name"),
                    "pending": c.get("pending", 0),
                    "idle": c.get("idle", 0),
                }
                for c in consumers
            ]
        except Exception as e:
            logger.warning(f"Failed to get consumer info: {e}")
            return []

    async def get_pending_count(self) -> int:
        """Get count of pending messages in this group.

        Returns:
            Number of pending messages
        """
        try:
            pending = await self.redis.xpending(
                self.request_stream,
                self.consumer_group,
            )
            # xpending returns: [count, min_id, max_id, [[consumer, count], ...]]
            if pending and len(pending) > 0:
                return pending[0] if isinstance(pending[0], int) else 0
            return 0
        except Exception as e:
            logger.warning(f"Failed to get pending count: {e}")
            return 0
