"""Demo orchestrator for scalability demonstrations.

Coordinates the creation of demo sessions and spawning of workers
to showcase the platform's ability to handle many simultaneous interviews.
"""

import asyncio
import json
import logging
import random
import uuid
from datetime import UTC, datetime

from api.admin_schemas import (
    DemoConfig,
    DemoLeaderboardEntry,
    DemoSession,
    DemoStatus,
)
from core.config import settings
from core.redis import get_redis_client
from services.demo_scripts import DemoScript, get_demo_scripts
from services.worker_spawner import worker_spawner

logger = logging.getLogger(__name__)

# Redis key for tracking cancelled demo sessions
CANCELLED_SESSIONS_KEY = "demo:cancelled_sessions"


class DemoOrchestrator:
    """Orchestrates scalability demo sessions."""

    def __init__(self):
        self._running = False
        self._config: DemoConfig | None = None
        self._sessions: dict[str, DemoSession] = {}
        self._session_tasks: dict[str, asyncio.Task] = {}
        self._started_at: str | None = None
        self._lock = asyncio.Lock()
        # Track session -> candidate name mapping for leaderboard
        self._session_candidates: dict[str, str] = {}

    async def get_status(self) -> DemoStatus:
        """Get current demo status including ELO leaderboard."""
        # Count completed sessions
        completed = sum(1 for s in self._sessions.values() if s.status == "completed")

        # Fetch ELO leaderboard if demo is running or recently ran
        leaderboard: list[DemoLeaderboardEntry] = []
        rankings_available = False
        role_id = self._config.role_id if self._config else None

        if role_id and completed >= 2:
            try:
                leaderboard, rankings_available = await self._fetch_leaderboard(role_id)
            except Exception as e:
                logger.warning(f"Failed to fetch ELO leaderboard: {e}")

        return DemoStatus(
            running=self._running,
            config=self._config,
            sessions=list(self._sessions.values()),
            workers_spawned=worker_spawner.get_active_count(),
            started_at=self._started_at,
            elo_leaderboard=leaderboard,
            rankings_available=rankings_available,
            completed_sessions=completed,
            role_id=role_id,
        )

    async def _fetch_leaderboard(
        self, role_id: str
    ) -> tuple[list[DemoLeaderboardEntry], bool]:
        """Fetch ELO rankings from Redis for the demo role.

        Args:
            role_id: The role ID to fetch rankings for

        Returns:
            Tuple of (leaderboard entries, rankings_available)
        """
        redis = get_redis_client()
        leaderboard: list[DemoLeaderboardEntry] = []

        try:
            # Get all candidates for this role
            role_candidates_key = f"role_candidates:{role_id}"
            candidate_ids = await redis.smembers(role_candidates_key)

            if not candidate_ids or len(candidate_ids) < 2:
                await redis.aclose()
                return [], False

            # Decode candidate IDs
            candidate_ids = [
                c.decode("utf-8") if isinstance(c, bytes) else c for c in candidate_ids
            ]

            # Get ratings for all candidates
            ratings = []
            for candidate_id in candidate_ids:
                rating_key = f"elo_rating:{role_id}:{candidate_id}"
                rating_data = await redis.get(rating_key)

                if rating_data:
                    import json

                    data_str = (
                        rating_data.decode("utf-8")
                        if isinstance(rating_data, bytes)
                        else rating_data
                    )
                    data = json.loads(data_str)
                    ratings.append((candidate_id, data))

            # Sort by rating (descending)
            ratings.sort(key=lambda x: x[1].get("rating", 1500), reverse=True)

            # Build leaderboard entries
            for rank, (candidate_id, data) in enumerate(ratings, 1):
                # Find session and candidate name for this candidate
                session_id = ""
                candidate_name = candidate_id.replace("-", " ").title()

                for sid, cname in self._session_candidates.items():
                    if cname.lower().replace(" ", "-") == candidate_id:
                        session_id = sid
                        candidate_name = cname
                        break

                # Try to get score percentage from weighted score
                score_percentage = None
                score_key = f"weighted_score:{role_id}:{candidate_id}"
                score_data = await redis.get(score_key)
                if score_data:
                    import json

                    score_str = (
                        score_data.decode("utf-8")
                        if isinstance(score_data, bytes)
                        else score_data
                    )
                    score = json.loads(score_str)
                    score_percentage = score.get("percentage")

                leaderboard.append(
                    DemoLeaderboardEntry(
                        candidate_id=candidate_id,
                        candidate_name=candidate_name,
                        session_id=session_id,
                        elo_rating=data.get("rating", 1500),
                        score_percentage=score_percentage,
                        rank=rank,
                        matches_played=data.get("matches_played", 0),
                        wins=data.get("wins", 0),
                        losses=data.get("losses", 0),
                        ties=data.get("ties", 0),
                    )
                )

            await redis.aclose()
            return leaderboard, len(leaderboard) >= 2

        except Exception as e:
            logger.error(f"Error fetching leaderboard: {e}")
            try:
                await redis.aclose()
            except Exception:
                pass
            return [], False

    async def start_demo(self, config: DemoConfig) -> DemoStatus:
        """Start the scalability demo.

        Args:
            config: Demo configuration

        Returns:
            Current demo status
        """
        async with self._lock:
            if self._running:
                return await self.get_status()

            self._running = True
            self._config = config
            self._started_at = datetime.now(UTC).isoformat()
            self._sessions.clear()
            self._session_tasks.clear()

            logger.info(
                f"Starting scalability demo with {config.session_count} sessions"
            )

            # Spawn initial workers if auto-scaling enabled
            if config.auto_spawn_workers:
                initial_workers = min(3, config.max_workers)
                logger.info(f"Spawning {initial_workers} initial workers")
                await worker_spawner.spawn_workers(initial_workers)

            # Get demo scripts
            scripts = get_demo_scripts(config.session_count)

            # Clear session-candidate mapping
            self._session_candidates.clear()

            # Start sessions with staggered timing
            for i, script in enumerate(scripts):
                session_id = f"demo-{uuid.uuid4().hex[:8]}"

                self._sessions[session_id] = DemoSession(
                    session_id=session_id,
                    candidate_name=script.profile.name,
                    status="pending",
                    turn_count=0,
                    script_progress=0,
                )

                # Track session -> candidate name for leaderboard
                self._session_candidates[session_id] = script.profile.name

                # Create task for this session
                task = asyncio.create_task(
                    self._run_demo_session(session_id, script, config)
                )
                self._session_tasks[session_id] = task

                # Stagger session starts (200-500ms apart) - no countdown
                await asyncio.sleep(random.uniform(0.2, 0.5))

            # Start worker scaling monitor if auto-scaling enabled
            if config.auto_spawn_workers:
                asyncio.create_task(self._scale_workers_loop(config))

            return await self.get_status()

    async def stop_demo(self) -> DemoStatus:
        """Stop the scalability demo.

        Returns:
            Final demo status
        """
        async with self._lock:
            if not self._running:
                return await self.get_status()

            logger.info("Stopping scalability demo")

            # Mark sessions as cancelled in Redis FIRST (before cancelling tasks)
            # This prevents workers from processing any more messages for these sessions
            await self._mark_sessions_cancelled()

            # Cancel all session tasks
            for task in self._session_tasks.values():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

            self._session_tasks.clear()

            # Update session statuses
            for session in self._sessions.values():
                session.status = "stopped"

            # Terminate spawned workers
            await worker_spawner.terminate_all()

            # Purge pending demo messages from the request stream
            await self._purge_demo_messages()

            # Clean up demo session contexts from Redis
            await self._cleanup_demo_sessions()

            self._running = False

            return await self.get_status()

    async def _mark_sessions_cancelled(self) -> None:
        """Mark all demo sessions as cancelled in Redis.

        Workers will check this before processing messages.
        """
        try:
            redis = get_redis_client()
            session_ids = list(self._sessions.keys())

            if session_ids:
                # Add all session IDs to the cancelled set
                await redis.sadd(CANCELLED_SESSIONS_KEY, *session_ids)
                # Set expiry so it auto-cleans up (1 hour)
                await redis.expire(CANCELLED_SESSIONS_KEY, 3600)
                logger.info(f"Marked {len(session_ids)} sessions as cancelled")

            await redis.aclose()
        except Exception as e:
            logger.warning(f"Error marking sessions as cancelled: {e}")

    async def _run_demo_session(
        self,
        session_id: str,
        script: DemoScript,
        config: DemoConfig,
    ) -> None:
        """Run a single demo session with scripted responses.

        Args:
            session_id: Session ID
            script: Demo script with profile and responses
            config: Demo configuration
        """
        try:
            redis = get_redis_client()

            # Update session status
            if session_id in self._sessions:
                self._sessions[session_id].status = "active"

            # Create the session by publishing system_init with JD for ELO scoring
            await self._publish_system_init(redis, session_id, script, config)

            # Wait for session to be initialized
            await asyncio.sleep(1)

            # Send responses with delays
            for i, response in enumerate(script.responses):
                if not self._running:
                    break

                # Update progress
                if session_id in self._sessions:
                    self._sessions[session_id].script_progress = i + 1
                    self._sessions[session_id].turn_count = i + 1

                # Publish candidate response
                await self._publish_candidate_response(redis, session_id, response)

                # Wait for AI response + configured delay
                delay_seconds = config.response_delay_ms / 1000
                # Add some randomness to make it look more natural
                delay_seconds += random.uniform(-0.5, 1.0)
                delay_seconds = max(0.5, delay_seconds)

                await asyncio.sleep(delay_seconds)

            # After all scripted responses, send a termination message
            # This triggers the interview end signal detection
            if self._running and script.responses:
                # Wait a bit longer for the final AI response to be processed
                final_delay = config.response_delay_ms / 1000 * 1.5
                await asyncio.sleep(final_delay)

                # Send natural goodbye message to trigger interview termination
                goodbye_message = (
                    "Thank you for this interview. "
                    "I think that covers everything. Goodbye!"
                )
                await self._publish_candidate_response(
                    redis, session_id, goodbye_message
                )

                if session_id in self._sessions:
                    self._sessions[session_id].script_progress += 1
                    self._sessions[session_id].turn_count += 1

            # Mark session as completed
            if session_id in self._sessions:
                self._sessions[session_id].status = "completed"

            await redis.aclose()

        except asyncio.CancelledError:
            logger.debug(f"Demo session {session_id} cancelled")
            raise
        except Exception as e:
            logger.error(f"Error in demo session {session_id}: {e}")
            if session_id in self._sessions:
                self._sessions[session_id].status = "error"

    async def _publish_system_init(
        self,
        redis,
        session_id: str,
        script: DemoScript,
        config: DemoConfig,
    ) -> None:
        """Publish system_init message to create session.

        Includes structured profile data for claim verification when available,
        and job description for ELO/skill tree scoring.
        """
        profile = script.profile

        # Build URLs
        urls = {}
        if profile.github_url:
            urls["github"] = profile.github_url
        if profile.linkedin_url:
            urls["linkedin"] = profile.linkedin_url

        # Use candidate name as candidate_id for ELO tracking
        # This makes leaderboard entries more readable
        candidate_id = profile.name.lower().replace(" ", "-")

        data = {
            "session_id": session_id,
            "message_type": "system_init",
            "content": "",
            "timestamp": datetime.now(UTC).isoformat(),
            "source": "demo",
            "candidate_name": profile.name,
            "candidate_id": candidate_id,
            "job_title": profile.job_title,
            # ELO/Skill Tree scoring fields
            "job_description": config.job_description,
            "role_id": config.role_id,
            "role_title": config.role_title,
        }

        if urls:
            data["urls"] = json.dumps(urls)
        if profile.resume_text:
            data["resume_text"] = profile.resume_text

        # Include structured profile data for demo sessions
        # This bypasses the crawler and provides pre-defined verification data
        if profile.github_data:
            data["github_data"] = json.dumps(profile.github_data)
        if profile.linkedin_data:
            data["linkedin_data"] = json.dumps(profile.linkedin_data)
        if profile.resume_data:
            data["resume_data"] = json.dumps(profile.resume_data)

        await redis.xadd(
            settings.request_stream, data, maxlen=settings.stream_maxlen, approximate=True
        )
        logger.debug(f"Published system_init for demo session {session_id}")

    async def _publish_candidate_response(
        self,
        redis,
        session_id: str,
        content: str,
    ) -> None:
        """Publish candidate response message."""
        data = {
            "session_id": session_id,
            "message_type": "candidate_response",
            "content": content,
            "timestamp": datetime.now(UTC).isoformat(),
            "source": "demo",
        }

        await redis.xadd(
            settings.request_stream, data, maxlen=settings.stream_maxlen, approximate=True
        )
        logger.debug(f"Published candidate response for demo session {session_id}")

    async def _scale_workers_loop(self, config: DemoConfig) -> None:
        """Monitor queue depth and scale workers accordingly."""
        try:
            redis = get_redis_client()

            while self._running:
                try:
                    # Get queue depth
                    info = await redis.xinfo_stream(settings.request_stream)
                    queue_length = info.get("length", 0)

                    # Get pending messages
                    try:
                        pending = await redis.xpending(
                            settings.request_stream,
                            "brain-workers",
                        )
                        pending_count = pending[0] if pending else 0
                    except Exception:
                        pending_count = 0

                    current_workers = worker_spawner.get_active_count()

                    # Scale up if queue is building up
                    if queue_length > 5 or pending_count > 3:
                        if current_workers < config.max_workers:
                            workers_to_add = min(
                                2,
                                config.max_workers - current_workers,
                            )
                            logger.info(
                                f"Scaling up: adding {workers_to_add} workers "
                                f"(queue: {queue_length}, pending: {pending_count})"
                            )
                            await worker_spawner.spawn_workers(workers_to_add)

                except Exception as e:
                    logger.warning(f"Error in worker scaling loop: {e}")

                await asyncio.sleep(2)  # Check every 2 seconds

            await redis.aclose()

        except asyncio.CancelledError:
            pass

    async def _cleanup_demo_sessions(self) -> None:
        """Clean up demo session data from Redis."""
        try:
            redis = get_redis_client()

            for session_id in self._sessions.keys():
                # Delete context
                context_key = f"context:{session_id}"
                await redis.delete(context_key)

                # Delete any locks
                lock_key = f"lock:session:{session_id}"
                await redis.delete(lock_key)

            # Clear the cancelled sessions set
            await redis.delete(CANCELLED_SESSIONS_KEY)

            await redis.aclose()
            logger.info(f"Cleaned up {len(self._sessions)} demo sessions")

        except Exception as e:
            logger.warning(f"Error cleaning up demo sessions: {e}")

    async def _purge_demo_messages(self) -> None:
        """Remove pending demo session messages from the request stream.

        This prevents workers from processing messages for stopped demo sessions.
        """
        try:
            redis = get_redis_client()
            demo_session_ids = set(self._sessions.keys())
            purged_count = 0

            # Read all pending messages from the stream
            # We use XRANGE to get all messages, then delete matching ones
            messages = await redis.xrange(settings.request_stream, "-", "+")

            for msg_id, data in messages:
                session_id = data.get("session_id", "")
                if session_id in demo_session_ids:
                    await redis.xdel(settings.request_stream, msg_id)
                    purged_count += 1

            await redis.aclose()
            logger.info(f"Purged {purged_count} demo messages from request stream")

        except Exception as e:
            logger.warning(f"Error purging demo messages: {e}")


# Global orchestrator instance
demo_orchestrator = DemoOrchestrator()
