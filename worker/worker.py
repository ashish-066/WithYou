"""Brain Worker - Main entry point for the interview processing worker.

This worker consumes messages from Redis Streams, processes them through
the LangGraph interview agent, and publishes responses back.
"""

import asyncio
import logging
import signal

from alex_db import dispose_engine
from alex_db.schema import ensure_schema

import core.db  # noqa: F401  (configures the database)
from brain.graph import create_interview_graph
from brain.processor import MessageProcessor
from core import readiness
from core.config import settings
from core.redis import check_redis_connection, close_redis_pool, get_redis_client
from sandbox.executor import ensure_sandbox_image
from services.metrics import MetricsCollector
from services.registry import WorkerRegistry
from services.state_manager import ContextManager
from services.streams import StreamManager, StreamMessage

logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Redis key for cancelled demo sessions (must match avatar service)
CANCELLED_SESSIONS_KEY = "demo:cancelled_sessions"

# Redis key prefix counting failed processing attempts per stream message
FAILED_ATTEMPTS_KEY_PREFIX = "stream:failed_attempts"


class BrainWorker:
    """Main worker class that processes interview messages."""

    def __init__(self):
        self.redis = None
        self.stream_manager = None
        self.processor = None
        self.registry = None
        self.metrics = None
        self.running = False
        # True while a message is being processed: a shutdown signal then lets
        # it finish instead of cancelling it mid-turn
        self.processing = False
        self._heartbeat_task = None
        self._sweep_task = None

    async def setup(self) -> bool:
        """Initialize the worker components.

        Returns:
            True if setup succeeded, False otherwise
        """
        logger.info(f"Setting up worker {settings.worker_id}")

        if not await check_redis_connection():
            logger.error("Failed to connect to Redis")
            return False

        # Development applies pending migrations; production refuses a stale schema
        try:
            await ensure_schema(auto_upgrade=settings.environment != "production")
        except Exception as e:
            logger.error(f"Database not ready: {e}")
            return False

        self.redis = await get_redis_client()

        # Initialize stream manager and processor
        self.stream_manager = StreamManager(self.redis)
        context_manager = ContextManager(self.redis)
        # No checkpointer: full state is loaded from/saved to Redis each message,
        # and an in-memory MemorySaver would only grow forever per session.
        graph = create_interview_graph(use_memory_saver=False)

        self.processor = MessageProcessor(
            redis=self.redis,
            graph=graph,
            context_manager=context_manager,
        )

        # Initialize registry and metrics
        self.registry = WorkerRegistry(self.redis)
        self.metrics = MetricsCollector(self.redis)

        # Create consumer group if needed, with retries
        for i in range(settings.redis_init_retries):
            try:
                await self.stream_manager.create_consumer_group()
                break  # Success, exit loop
            except Exception as e:
                retries = settings.redis_init_retries
                logger.warning(f"Attempt {i + 1}/{retries} to create consumer group failed: {e}")
                await asyncio.sleep(settings.redis_init_delay_seconds)
        else:
            logger.error("Failed to create consumer group after multiple retries.")
            return False

        # Pull the sandbox image now rather than during a candidate's first run
        if settings.sandbox_mode == "docker" and not await ensure_sandbox_image():
            logger.error(
                f"Sandbox image {settings.sandbox_image} is not available; "
                "code runs will report the sandbox as unavailable"
            )

        # Register this worker
        await self.registry.register()
        readiness.mark_ready()

        logger.info(f"Worker {settings.worker_id} setup complete")
        return True

    async def _heartbeat_loop(self) -> None:
        """Background task that sends periodic heartbeats."""
        while self.running:
            try:
                await self.registry.heartbeat()
                readiness.mark_ready()
                await asyncio.sleep(settings.heartbeat_interval_seconds)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"Heartbeat error: {e}")
                await asyncio.sleep(5)

    async def _sweep_loop(self) -> None:
        """End interviews nobody is attending (see services/inactivity_sweep.py)."""
        from services.inactivity_sweep import sweep_inactive

        while self.running:
            try:
                await sweep_inactive(self.redis)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"Inactivity sweep error: {e}")
            await asyncio.sleep(settings.inactivity_sweep_seconds)

    async def _is_session_cancelled(self, session_id: str) -> bool:
        """Check if a session has been cancelled (e.g., demo stopped).

        Args:
            session_id: The session ID to check

        Returns:
            True if the session is in the cancelled set
        """
        try:
            result = await self.redis.sismember(CANCELLED_SESSIONS_KEY, session_id)
            return bool(result)
        except Exception:
            return False

    @staticmethod
    def _failure_key(message_id: str) -> str:
        return f"{FAILED_ATTEMPTS_KEY_PREFIX}:{message_id}"

    async def _record_failure(self, message: StreamMessage, error: str) -> None:
        """Count a failed attempt; give up (ACK) once max_delivery_attempts is hit.

        Unacked messages are retried via periodic reclaim, so without a cap a
        message that always fails would be retried forever.
        """
        try:
            key = self._failure_key(message.message_id)
            attempts = await self.redis.incr(key)
            await self.redis.expire(key, 3600)
            if attempts >= settings.max_delivery_attempts:
                logger.error(
                    f"Dropping message {message.message_id} for session "
                    f"{message.session_id} after {attempts} failed attempts: {error}"
                )
                await self.stream_manager.dead_letter(message, error, attempts)
                await self.stream_manager.ack(message.message_id)
                await self.redis.delete(key)
        except Exception as e:
            logger.warning(f"Failed to record failure for {message.message_id}: {e}")

    async def _keep_message_claimed(self, message_id: str) -> None:
        """Stop other workers' periodic reclaim from taking a message we're still processing."""
        interval = settings.reclaim_min_idle_ms / 3000
        while True:
            await asyncio.sleep(interval)
            try:
                await self.stream_manager.touch(message_id)
            except Exception as e:
                logger.warning(f"Failed to refresh claim on {message_id}: {e}")

    async def process_message(self, message: StreamMessage) -> None:
        """Process a single message from the stream.

        Args:
            message: The stream message to process
        """
        # Check if this session has been cancelled (e.g., demo stopped)
        if await self._is_session_cancelled(message.session_id):
            logger.info(
                f"Skipping message {message.message_id} for cancelled session {message.session_id}"
            )
            # Acknowledge the message so it's removed from the stream
            await self.stream_manager.ack(message.message_id)
            return

        logger.info(f"Processing message {message.message_id} for session {message.session_id}")

        # Start metrics tracking
        msg_metrics = self.metrics.start_message(message.message_id, message.session_id)

        # Update worker status to busy
        await self.registry.update_status(
            "busy",
            {"current_session": message.session_id},
        )

        keepalive_task = asyncio.create_task(self._keep_message_claimed(message.message_id))

        # Echo the avatar's turn number so it can drop replies to
        # turns the candidate has already followed up on
        turn_seq = message.raw_data.get("turn_seq")

        async def publish(content: str) -> None:
            await self.stream_manager.publish_response(
                session_id=message.session_id,
                content=content,
                extra_fields={"reply_to_seq": turn_seq} if turn_seq else None,
            )

        try:
            result = await self.processor.process_with_retry(message, publish=publish)

            if result.get("published") and not result["success"]:
                # The reply already reached the candidate; retrying would speak a
                # second one, so give up on this message instead
                logger.error(
                    f"Message {message.message_id} failed after its reply was sent: "
                    f"{result.get('error')}; not retrying"
                )
                # Its state update may be lost: keep it for inspection
                await self.stream_manager.dead_letter(
                    message, f"failed after reply was sent: {result.get('error')}", 1
                )
                await self.stream_manager.ack(message.message_id)
                await self.metrics.record_message(
                    msg_metrics, success=False, error=str(result.get("error"))
                )
                return

            if result["success"]:
                # Nodes send the reply early (before scoring); otherwise send it now
                if result.get("response") and not result.get("published"):
                    await publish(result["response"])

                # The interview just ended: the voice agent hangs up once it has
                # spoken the goodbye above (replies are spoken in order)
                if result.get("ended_now"):
                    await self.stream_manager.publish_response(
                        session_id=message.session_id,
                        content="",
                        message_type="interview_ended",
                        extra_fields={"end_reason": result.get("end_reason") or "completed"},
                    )

                await self.stream_manager.ack(message.message_id)
                await self.redis.delete(self._failure_key(message.message_id))

                # Record successful processing
                brain_mode = result.get("brain_mode", "fast")
                await self.metrics.record_message(
                    msg_metrics,
                    success=True,
                    brain_mode=brain_mode,
                )

                logger.info(
                    f"Successfully processed message {message.message_id}, "
                    f"response published (mode: {brain_mode})"
                )
            else:
                error_msg = result.get("error", "unknown error")
                await self.metrics.record_message(
                    msg_metrics,
                    success=False,
                    error=error_msg,
                )
                logger.error(f"Failed to process message {message.message_id}: {error_msg}")
                await self._record_failure(message, error_msg)

        except Exception as e:
            await self.metrics.record_message(
                msg_metrics,
                success=False,
                error=str(e),
            )
            logger.exception(f"Error processing message {message.message_id}: {e}")
            await self._record_failure(message, str(e))

        finally:
            keepalive_task.cancel()
            # Update worker status back to active
            await self.registry.update_status("active")

    async def _process_one(self, message: StreamMessage) -> None:
        self.processing = True
        try:
            await self.process_message(message)
        finally:
            self.processing = False

    async def run(self) -> None:
        """Main worker loop."""
        if not await self.setup():
            logger.error("Failed to setup worker, exiting")
            return

        self.running = True

        # Start heartbeat background task
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        self._sweep_task = asyncio.create_task(self._sweep_loop())

        logger.info(
            f"Worker {settings.worker_id} starting main loop, "
            f"consuming from {settings.request_stream}"
        )

        try:
            # Process any pending messages first
            logger.info("Checking for pending messages...")
            async for message in self.stream_manager.consume_pending():
                if not self.running:
                    break
                await self._process_one(message)
                if not self.running:
                    break

            # Main consumption loop
            logger.info("Starting main consumption loop...")
            async for message in self.stream_manager.consume():
                if not self.running:
                    break
                await self._process_one(message)
                if not self.running:
                    break

        except asyncio.CancelledError:
            logger.info("Worker cancelled, shutting down...")
        except Exception as e:
            logger.exception(f"Worker error: {e}")
        finally:
            await self.shutdown()

    async def shutdown(self) -> None:
        """Gracefully shutdown the worker."""
        logger.info(f"Shutting down worker {settings.worker_id}")
        self.running = False
        readiness.mark_not_ready()

        # Cancel background tasks
        for task in (self._heartbeat_task, self._sweep_task):
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        # Deregister from Redis
        if self.registry:
            await self.registry.deregister()

        # Remove from consumer group
        if self.stream_manager:
            await self.stream_manager.remove_consumer()

        # Close Redis pool and database connections
        await close_redis_pool()
        await dispose_engine()

        logger.info("Worker shutdown complete")


async def main():
    """Entry point for the worker."""
    worker = BrainWorker()
    run_task: asyncio.Task | None = None

    # Setup signal handlers for graceful shutdown
    loop = asyncio.get_running_loop()

    def signal_handler():
        # First signal: stop taking messages, but let the current one finish
        # (cancelling it mid-turn could leave its reply sent but its state
        # unsaved). A second signal, or an idle worker, stops at once. Messages
        # read but not processed stay pending and are reclaimed by other workers.
        if worker.running and worker.processing:
            logger.info("Received shutdown signal; finishing the current message first")
            worker.running = False
            return
        logger.info("Received shutdown signal")
        worker.running = False
        # Cancel the run task to break out of the blocking consume loop
        if run_task and not run_task.done():
            run_task.cancel()

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, signal_handler)

    run_task = asyncio.create_task(worker.run())
    await run_task


if __name__ == "__main__":
    asyncio.run(main())
