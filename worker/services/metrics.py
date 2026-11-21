"""Metrics collector for tracking worker performance.

Collects and publishes throughput and latency metrics to Redis
for dashboard visualization.
"""

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

from redis.asyncio import Redis

from core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class MessageMetrics:
    """Metrics for a single message processing."""

    message_id: str
    session_id: str
    start_time: float = field(default_factory=time.monotonic)
    end_time: float | None = None
    success: bool = False
    brain_mode: str = "unknown"
    error: str | None = None

    @property
    def duration_ms(self) -> float:
        """Processing duration in milliseconds."""
        if self.end_time is None:
            return 0
        return (self.end_time - self.start_time) * 1000


class MetricsCollector:
    """Collects and publishes worker metrics to Redis.

    Tracks:
    - Messages processed (success/failure)
    - Processing latency
    - Throughput (messages per second)
    - Brain mode distribution
    """

    METRICS_KEY_PREFIX = "worker:metrics"
    THROUGHPUT_KEY = "ops:throughput"

    def __init__(self, redis: Redis):
        self.redis = redis
        self.worker_id = settings.worker_id
        self._start_time = datetime.now(timezone.utc)

        # In-memory counters
        self._messages_processed = 0
        self._messages_failed = 0
        self._total_latency_ms = 0.0
        self._fast_brain_count = 0
        self._slow_brain_count = 0

        # Recent latencies for percentile calculation
        self._recent_latencies: list[float] = []
        self._max_recent = 100

    @property
    def metrics_key(self) -> str:
        """Redis key for this worker's metrics."""
        return f"{self.METRICS_KEY_PREFIX}:{self.worker_id}"

    def start_message(self, message_id: str, session_id: str) -> MessageMetrics:
        """Start tracking a message processing.

        Args:
            message_id: Redis message ID
            session_id: Interview session ID

        Returns:
            MessageMetrics object to track this message
        """
        return MessageMetrics(message_id=message_id, session_id=session_id)

    async def record_message(
        self,
        metrics: MessageMetrics,
        success: bool,
        brain_mode: str = "fast",
        error: str | None = None,
    ) -> None:
        """Record completion of message processing.

        Args:
            metrics: MessageMetrics from start_message
            success: Whether processing succeeded
            brain_mode: Which brain processed (fast/slow)
            error: Error message if failed
        """
        metrics.end_time = time.monotonic()
        metrics.success = success
        metrics.brain_mode = brain_mode
        metrics.error = error

        # Update in-memory counters
        if success:
            self._messages_processed += 1
        else:
            self._messages_failed += 1

        self._total_latency_ms += metrics.duration_ms

        if brain_mode == "fast":
            self._fast_brain_count += 1
        elif brain_mode == "slow":
            self._slow_brain_count += 1

        # Track recent latencies
        self._recent_latencies.append(metrics.duration_ms)
        if len(self._recent_latencies) > self._max_recent:
            self._recent_latencies.pop(0)

        # Publish to Redis
        await self._publish_metrics()
        await self._record_throughput_event()

    async def _publish_metrics(self) -> None:
        """Publish current metrics to Redis hash."""
        try:
            uptime_seconds = (datetime.now(timezone.utc) - self._start_time).total_seconds()

            total_messages = self._messages_processed + self._messages_failed
            avg_latency = self._total_latency_ms / total_messages if total_messages > 0 else 0

            # Calculate p50 and p95 from recent latencies
            p50, p95 = 0.0, 0.0
            if self._recent_latencies:
                sorted_latencies = sorted(self._recent_latencies)
                n = len(sorted_latencies)
                p50 = sorted_latencies[n // 2]
                p95 = sorted_latencies[int(n * 0.95)] if n >= 20 else sorted_latencies[-1]

            metrics_data = {
                "worker_id": self.worker_id,
                "messages_processed": str(self._messages_processed),
                "messages_failed": str(self._messages_failed),
                "total_messages": str(total_messages),
                "avg_latency_ms": f"{avg_latency:.2f}",
                "p50_latency_ms": f"{p50:.2f}",
                "p95_latency_ms": f"{p95:.2f}",
                "fast_brain_count": str(self._fast_brain_count),
                "slow_brain_count": str(self._slow_brain_count),
                "uptime_seconds": f"{uptime_seconds:.0f}",
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }

            await self.redis.hset(self.metrics_key, mapping=metrics_data)
            # Set TTL to auto-expire old metrics
            await self.redis.expire(self.metrics_key, 300)  # 5 minutes

        except Exception as e:
            logger.warning(f"Failed to publish metrics: {e}")

    async def _record_throughput_event(self) -> None:
        """Record a throughput event for time-series tracking."""
        try:
            # Use Redis list as a simple time-series
            # Each entry is a timestamp of a processed message
            now = datetime.now(timezone.utc).isoformat()
            await self.redis.lpush(self.THROUGHPUT_KEY, now)

            # Trim to last 1000 events
            await self.redis.ltrim(self.THROUGHPUT_KEY, 0, 999)

        except Exception as e:
            logger.debug(f"Failed to record throughput event: {e}")

    async def get_metrics(self) -> dict:
        """Get current metrics from Redis."""
        try:
            data = await self.redis.hgetall(self.metrics_key)
            return {k: v for k, v in data.items()}
        except Exception:
            return {}

    @classmethod
    async def get_all_worker_metrics(cls, redis: Redis) -> list[dict]:
        """Get metrics for all workers.

        Args:
            redis: Redis client

        Returns:
            List of metrics dicts for each worker
        """
        metrics = []
        cursor = 0

        while True:
            cursor, keys = await redis.scan(
                cursor,
                match=f"{cls.METRICS_KEY_PREFIX}:*",
                count=100,
            )

            for key in keys:
                data = await redis.hgetall(key)
                if data:
                    metrics.append({k: v for k, v in data.items()})

            if cursor == 0:
                break

        return metrics

    @classmethod
    async def get_aggregate_metrics(cls, redis: Redis) -> dict:
        """Get aggregated metrics across all workers.

        Args:
            redis: Redis client

        Returns:
            Aggregate metrics dict
        """
        all_metrics = await cls.get_all_worker_metrics(redis)

        if not all_metrics:
            return {
                "total_workers": 0,
                "total_messages": 0,
                "total_failed": 0,
                "avg_latency_ms": 0,
                "success_rate": 0,
            }

        total_messages = sum(int(m.get("total_messages", 0)) for m in all_metrics)
        total_failed = sum(int(m.get("messages_failed", 0)) for m in all_metrics)
        total_processed = sum(int(m.get("messages_processed", 0)) for m in all_metrics)

        # Weighted average latency
        weighted_latency = sum(
            float(m.get("avg_latency_ms", 0)) * int(m.get("total_messages", 0)) for m in all_metrics
        )
        avg_latency = weighted_latency / total_messages if total_messages > 0 else 0

        success_rate = total_processed / total_messages * 100 if total_messages > 0 else 100

        return {
            "total_workers": len(all_metrics),
            "total_messages": total_messages,
            "total_processed": total_processed,
            "total_failed": total_failed,
            "avg_latency_ms": round(avg_latency, 2),
            "success_rate": round(success_rate, 2),
        }

    @classmethod
    async def get_throughput(cls, redis: Redis, window_seconds: int = 60) -> dict:
        """Calculate messages per second over a time window.

        Args:
            redis: Redis client
            window_seconds: Time window to calculate throughput

        Returns:
            Throughput metrics
        """
        try:
            # Get all recent events
            events = await redis.lrange(cls.THROUGHPUT_KEY, 0, -1)
            if not events:
                return {"messages_per_second": 0, "total_in_window": 0}

            now = datetime.now(timezone.utc)
            count_in_window = 0

            for event in events:
                try:
                    event_time = datetime.fromisoformat(event)
                    delta = (now - event_time).total_seconds()
                    if delta <= window_seconds:
                        count_in_window += 1
                except (ValueError, TypeError):
                    continue

            messages_per_second = count_in_window / window_seconds

            return {
                "messages_per_second": round(messages_per_second, 2),
                "total_in_window": count_in_window,
                "window_seconds": window_seconds,
            }

        except Exception as e:
            logger.warning(f"Failed to calculate throughput: {e}")
            return {"messages_per_second": 0, "total_in_window": 0}
