"""Worker registry for tracking active workers via Redis.

Provides heartbeat-based registration so the dashboard can discover
and monitor active workers in real-time.
"""

import json
import logging
import socket
from datetime import datetime, timezone

from redis.asyncio import Redis

from core.config import settings

logger = logging.getLogger(__name__)


class WorkerRegistry:
    """Manages worker registration and heartbeat in Redis.

    Workers register on startup and send periodic heartbeats.
    Registration automatically expires if heartbeat stops (TTL-based).
    """

    HEARTBEAT_KEY_PREFIX = "worker:heartbeat"
    METRICS_KEY_PREFIX = "worker:metrics"

    def __init__(self, redis: Redis):
        self.redis = redis
        self.worker_id = settings.worker_id
        self.consumer_name = settings.consumer_name
        self._registered = False
        self._hostname = socket.gethostname()

    @property
    def heartbeat_key(self) -> str:
        """Redis key for this worker's heartbeat."""
        return f"{self.HEARTBEAT_KEY_PREFIX}:{self.worker_id}"

    def _get_registration_data(self) -> dict:
        """Build registration payload."""
        return {
            "worker_id": self.worker_id,
            "consumer_name": self.consumer_name,
            "hostname": self._hostname,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "last_heartbeat": datetime.now(timezone.utc).isoformat(),
            "status": "active",
            "consumer_group": settings.consumer_group,
            "request_stream": settings.request_stream,
        }

    async def register(self) -> None:
        """Register this worker in Redis.

        Sets a key with TTL that will auto-expire if heartbeat stops.
        """
        try:
            data = self._get_registration_data()
            await self.redis.set(
                self.heartbeat_key,
                json.dumps(data),
                ex=settings.heartbeat_ttl_seconds,
            )
            self._registered = True
            logger.info(
                f"Worker {self.worker_id} registered with TTL {settings.heartbeat_ttl_seconds}s"
            )
        except Exception as e:
            logger.error(f"Failed to register worker: {e}")
            raise

    async def heartbeat(self) -> None:
        """Send heartbeat to keep registration alive.

        Updates the last_heartbeat timestamp and refreshes TTL.
        """
        if not self._registered:
            await self.register()
            return

        try:
            # Get current data, update heartbeat, reset TTL
            current_data = await self.redis.get(self.heartbeat_key)
            if current_data:
                data = json.loads(current_data)
                data["last_heartbeat"] = datetime.now(timezone.utc).isoformat()
            else:
                # Key expired, re-register
                data = self._get_registration_data()

            await self.redis.set(
                self.heartbeat_key,
                json.dumps(data),
                ex=settings.heartbeat_ttl_seconds,
            )
            logger.debug(f"Worker {self.worker_id} heartbeat sent")
        except Exception as e:
            logger.warning(f"Failed to send heartbeat: {e}")

    async def update_status(self, status: str, extra: dict | None = None) -> None:
        """Update worker status in registry.

        Args:
            status: One of 'active', 'busy', 'slow_task', 'idle'
            extra: Additional fields to include
        """
        try:
            current_data = await self.redis.get(self.heartbeat_key)
            if current_data:
                data = json.loads(current_data)
                data["status"] = status
                data["last_heartbeat"] = datetime.now(timezone.utc).isoformat()
                if extra:
                    data.update(extra)

                await self.redis.set(
                    self.heartbeat_key,
                    json.dumps(data),
                    ex=settings.heartbeat_ttl_seconds,
                )
        except Exception as e:
            logger.warning(f"Failed to update worker status: {e}")

    async def deregister(self) -> None:
        """Remove this worker from the registry.

        Called during graceful shutdown.
        """
        try:
            # Delete heartbeat key
            await self.redis.delete(self.heartbeat_key)
            logger.info(f"Worker {self.worker_id} heartbeat key deleted")

            # Consumer group removal is done by StreamManager.remove_consumer,
            # which first checks for pending messages (deleting would lose them).

            self._registered = False
            logger.info(f"Worker {self.worker_id} deregistered")
        except Exception as e:
            logger.error(f"Failed to deregister worker: {e}")

    @classmethod
    async def list_workers(cls, redis: Redis) -> list[dict]:
        """List all registered workers.

        Args:
            redis: Redis client

        Returns:
            List of worker info dicts
        """
        workers = []
        cursor = 0

        while True:
            cursor, keys = await redis.scan(
                cursor,
                match=f"{cls.HEARTBEAT_KEY_PREFIX}:*",
                count=100,
            )

            for key in keys:
                data = await redis.get(key)
                if data:
                    try:
                        workers.append(json.loads(data))
                    except json.JSONDecodeError:
                        pass

            if cursor == 0:
                break

        return workers

    @classmethod
    async def get_worker_count(cls, redis: Redis) -> int:
        """Get count of registered workers."""
        count = 0
        cursor = 0

        while True:
            cursor, keys = await redis.scan(
                cursor,
                match=f"{cls.HEARTBEAT_KEY_PREFIX}:*",
                count=100,
            )
            count += len(keys)

            if cursor == 0:
                break

        return count
