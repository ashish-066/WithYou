"""Message processor - orchestrates graph invocation with state management.

This module ties together the state manager, stream manager, and LangGraph
to process interview messages with proper locking and persistence.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from redis.asyncio import Redis

from brain import interview_flow, talk, understanding
from brain.brains.router import run_prefilter
from brain.graph import create_interview_graph
from brain.language_switch import requested_language
from brain.services.reply_publisher import (
    ReplyPublisher,
    bind_reply_publisher,
    reset_reply_publisher,
)
from services.interview_store import save_interview_outcome, state_from_saved
from services.state_manager import ContextManager, LockAcquisitionError
from services.streams import StreamMessage
from services.transcript import append_message, load_transcript

logger = logging.getLogger(__name__)


# Messages that come from the candidate's side of the call
# Languages the buddy speaks (BCP-47, as Sarvam reports them)
SUPPORTED_LANGUAGES = {"ml-IN", "te-IN", "en-IN"}

CANDIDATE_TURN_TYPES = {"candidate_response", "question_unanswered", "candidate_returned"}


def _int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


class MessageProcessor:
    """Processes interview messages through the LangGraph.

    Handles the full lifecycle of message processing:
    1. Acquire distributed lock for the session
    2. Load context from Redis
    3. Invoke the LangGraph with the new message
    4. Save updated context to Redis
    5. Release the lock

    Usage:
        processor = MessageProcessor(redis_client)
        result = await processor.process(message)
    """

    def __init__(
        self,
        redis: Redis,
        graph: Any | None = None,
        context_manager: ContextManager | None = None,
    ):
        self.redis = redis
        self.context_manager = context_manager or ContextManager(redis)
        self.graph = graph or create_interview_graph(use_memory_saver=False)

    async def process(
        self, message: StreamMessage, publish: ReplyPublisher | None = None
    ) -> dict[str, Any]:
        """Process a message from the stream.

        Args:
            message: The StreamMessage to process
            publish: Sends a reply to the candidate. If given, nodes call it as
                soon as the reply is ready, and the result has "published": True

        Returns:
            Dict with processing result including response

        Raises:
            LockAcquisitionError: If lock cannot be acquired
        """
        session_id = message.session_id
        content = message.content

        logger.info(f"Processing message for session {session_id}: {content[:50]}...")

        # Acquire distributed lock
        lock_token = await self.context_manager.acquire_lock(session_id)
        if not lock_token:
            raise LockAcquisitionError(f"Could not acquire lock for session {session_id}")

        renew_task = asyncio.create_task(self._renew_lock(session_id, lock_token))

        # At most one reply per message reaches the candidate, even if a node
        # falls back to a second response after publishing the first
        published = False

        async def publish_once(text: str) -> None:
            nonlocal published
            if published or publish is None:
                return
            await publish(text)
            published = True

        try:
            # Load current context
            state = await self.context_manager.get_context(session_id)
            was_ended = bool(state.get("interview_ended"))

            # After the end, nothing the candidate says or does changes the
            # interview (and must not trigger another closing report)
            if was_ended and message.message_type in (*CANDIDATE_TURN_TYPES, "end_call"):
                logger.info(f"Ignoring {message.message_type} for ended session {session_id}")
                return {"session_id": session_id, "response": "", "turn_count": state.get("turn_count", 0), "success": True}

            # Session setup (skill tree from the description sent by the API)
            if message.message_type == "system_init":
                raw_data = message.raw_data
                if raw_data.get("language") in SUPPORTED_LANGUAGES:
                    state["language"] = raw_data["language"]
                if raw_data.get("mode") in talk.MODES:
                    state["session_mode"] = raw_data["mode"]
                if not raw_data.get("job_description"):
                    # Setup only: nothing to say (the voice agent greets)
                    await self.context_manager.update_context(session_id, state)
                    return {"session_id": session_id, "response": "", "turn_count": state.get("turn_count", 0), "success": True}
                # Initialize skill tree scoring if job description provided
                job_description = raw_data.get("job_description")
                if job_description:
                    state["job_description"] = job_description
                    try:
                        from core.config import settings
                        from scoring.integration import ScoringIntegration

                        role_id = raw_data.get("role_id", f"role-{session_id[:8]}")
                        role_title = raw_data.get("role_title", "")
                        candidate_id = state.get("candidate_id") or session_id

                        scoring = ScoringIntegration(self.redis)
                        # Bounded: several Gemini calls in a row, and this worker
                        # handles no other interview until it returns.
                        skill_tree_state = await asyncio.wait_for(
                            scoring.initialize_scoring(
                                session_id=session_id,
                                candidate_id=candidate_id,
                                job_description=job_description,
                                role_id=role_id,
                            ),
                            timeout=settings.scoring_init_timeout_seconds,
                        )

                        # Add role_title if available
                        if role_title:
                            skill_tree_state["role_title"] = role_title

                        state["skill_tree"] = skill_tree_state
                        logger.info(
                            f"Initialized skill tree scoring for session {session_id} "
                            f"with {len(skill_tree_state.get('skill_weights', {}))} skills"
                        )
                    except Exception as e:
                        # str(TimeoutError()) is empty, so name the type
                        logger.error(
                            f"Failed to initialize skill tree scoring: {type(e).__name__}: {e}"
                        )

            # Handle end_call message to trigger conclude_interview node
            elif message.message_type == "end_call":
                logger.info(f"Processing end_call for session {session_id}")
                state["interview_ended"] = True
                state["end_reason"] = message.raw_data.get("end_reason", "user_ended")
                # Set input_classification to end_signal to ensure routing to conclude node
                state["input_classification"] = "end_signal"
                content = ""  # No content needed for end call

            # Write the report again (it failed earlier)
            elif message.message_type == "regenerate_report":
                return await self._regenerate_report(session_id, state)

            # Interview progress: time budget, wrap-up, confirming a goodbye,
            # unanswered questions, returns after an absence (brain/interview_flow.py)
            now = datetime.now(timezone.utc)
            decision: interview_flow.Decision | None = None
            if message.message_type == "candidate_response":
                # The language the learner just spoke (speech recognition detects it):
                # the buddy answers in it
                spoken = message.raw_data.get("language")
                if spoken in SUPPORTED_LANGUAGES:
                    state["language"] = spoken
                # ...unless they ask to change it ("మలయాళంలో చెప్పు", "speak English")
                asked = requested_language(message.content, state.get("language"))
                if asked:
                    logger.info(f"Learner asked to switch {session_id} to {asked}")
                    state["language"] = asked
                decision = interview_flow.before_candidate_turn(state, message.content, now)
                state["flow"] = decision.flow
            elif message.message_type == "question_unanswered":
                decision = interview_flow.on_unanswered(state)
                content = "[NO ANSWER]"
            elif message.message_type == "candidate_returned":
                decision = interview_flow.on_returned(state)
                content = "[CANDIDATE RETURNED]"
            # Gentle evaluator (brain/understanding.py): is this an answer to the
            # buddy's check question, and does a vague one get a follow-up?
            state["answering_check"] = False
            state["check_target"] = ""
            talking = talk.is_talk(state)  # "Just talk" mode: no study bookkeeping
            if talking and decision is not None:
                key = next((k for k, v in interview_flow.INSTRUCTIONS.items() if v == decision.instruction), None)
                if key in talk.TALK_INSTRUCTIONS:
                    decision.instruction = talk.TALK_INSTRUCTIONS[key]
            if message.message_type == "candidate_response" and not talking and not (decision and decision.instruction):
                intent = run_prefilter({**state, "current_input": message.content})
                if understanding.answering_a_check(state) and understanding.is_answer(
                    intent.classification, intent.confidence
                ):
                    state["answering_check"] = True
                    state["understanding"], follow_up = understanding.before_reply(state, message.content)
                    if decision is not None and follow_up:
                        decision.instruction = follow_up
                target = understanding.next_point(state)
                state["check_target"] = target["id"] if target else ""
            # Safety first, in every mode: talk of self-harm gets a caring, serious
            # reply that points to real help (brain/talk.py), overriding anything else
            if message.message_type == "candidate_response" and talk.in_crisis(message.content):
                logger.warning(f"Crisis language in session {session_id}: replying with safety guidance")
                if decision is None:
                    decision = interview_flow.Decision("continue", "", None, state.get("flow") or {})
                decision.instruction = talk.CRISIS_INSTRUCTION
                state["crisis_flagged"] = True  # the end card repeats the helpline
                if decision.action == "conclude":
                    decision.action, decision.end_reason = "continue", None
                state["answering_check"] = False
            if decision is not None:
                state["flow"] = decision.flow
                state["interviewer_instruction"] = decision.instruction
                if decision.action == "conclude":
                    state["interview_ended"] = True
                    state["end_reason"] = decision.end_reason
                    state["input_classification"] = "end_signal"

            # Update state with new input
            state["current_input"] = content
            state["last_updated"] = now.isoformat()


            # Invoke the graph
            # The thread_id ensures checkpointing works correctly
            config = {"configurable": {"thread_id": session_id}}

            # Let nodes send the reply as soon as it exists (before scoring)
            # The candidate's words go into the full transcript before the graph
            # runs, so a node that reads it (the closing report) sees this answer
            if message.message_type == "candidate_response":
                await append_message(
                    self.redis, session_id, "user", message.content,
                    (state.get("turn_count") or 0) + 1, source_id=message.message_id,
                )

            previous_reply = state.get("response") or ""
            token = bind_reply_publisher(publish_once if publish else None)
            try:
                result = await self.graph.ainvoke(state, config=config)
            finally:
                reset_reply_publisher(token)

            # The instruction was for this turn only; ratings are tracked for stability
            result["interviewer_instruction"] = ""
            if message.message_type == "candidate_response" and not result.get("interview_ended"):
                result["flow"] = interview_flow.record_levels(result)

            # Save updated context
            await self.context_manager.update_context(session_id, result)

            # Full transcript (state keeps only the last few messages)
            turn = result.get("turn_count")
            reply = result.get("response") or ""
            # A reply carried over unchanged in state (no node answered) isn't new
            is_new = message.message_type == "candidate_response" or reply != previous_reply
            if isinstance(reply, str) and reply.strip() and is_new:
                await append_message(self.redis, session_id, "assistant", reply, turn)

            # Ended sessions: copy the outcome to Postgres
            if result.get("interview_ended"):
                await save_interview_outcome(
                    session_id, result, await load_transcript(self.redis, session_id)
                )

            logger.info(
                f"Processed message for session {session_id}, turn {result.get('turn_count', 0)}"
            )

            return {
                "session_id": session_id,
                "response": result.get("response", ""),
                "turn_count": result.get("turn_count", 0),
                "success": True,
                "published": published,
                # Tells the voice agent to hang up after speaking the goodbye
                "ended_now": bool(result.get("interview_ended")) and not was_ended,
                "end_reason": result.get("end_reason"),
            }

        except Exception as e:
            logger.error(f"Error processing message for {session_id}: {e}")
            return {
                "session_id": session_id,
                "error": str(e),
                "success": False,
                "published": published,
            }

        finally:
            renew_task.cancel()
            # Always release the lock
            await self.context_manager.release_lock(session_id, lock_token)

    async def _regenerate_report(self, session_id: str, state: dict) -> dict[str, Any]:
        """Run the report step again for an ended interview, and save it."""
        from brain.tools.slow.report_generator import (
            generate_analytics_report,
            generate_descriptive_report,
        )

        live = bool(state.get("interview_ended") and state.get("messages"))
        if not live:
            saved = await state_from_saved(session_id)
            if saved is None:
                return {"session_id": session_id, "response": "", "turn_count": 0, "success": True}
            state = {**state, **saved}
        if state.get("descriptive_report"):
            return {"session_id": session_id, "response": "", "turn_count": state.get("turn_count", 0), "success": True}

        state["report_attempts"] = int(state.get("report_attempts") or 0) + 1
        desc = await generate_descriptive_report(state)
        if desc.success and desc.data:
            state["descriptive_report"] = desc.data
            if not state.get("analytics_data"):
                analytics = await generate_analytics_report(state)
                if analytics.success:
                    state["analytics_data"] = analytics.data
            state["report_status"] = "completed"
            logger.info(f"Report written on retry for {session_id} (attempt {state['report_attempts']})")
        else:
            state["report_status"] = "failed"
            logger.error(f"Report retry failed for {session_id}: {desc.error}")
        state["last_updated"] = datetime.now(timezone.utc).isoformat()
        if live:
            await self.context_manager.update_context(session_id, state)
        if state.get("descriptive_report"):
            await save_interview_outcome(session_id, state, await load_transcript(self.redis, session_id))
        return {"session_id": session_id, "response": "", "turn_count": state.get("turn_count", 0), "success": True}

    async def _renew_lock(self, session_id: str, lock_token: str) -> None:
        """Keep the session lock alive while a (possibly slow) graph run is in progress."""
        interval = self.context_manager.lock_ttl_ms / 3000
        while True:
            await asyncio.sleep(interval)
            try:
                if not await self.context_manager.extend_lock(session_id, lock_token):
                    logger.error(f"Lost lock for session {session_id} during processing")
                    return
            except Exception as e:
                logger.warning(f"Failed to renew lock for session {session_id}: {e}")

    async def process_with_retry(
        self,
        message: StreamMessage,
        max_retries: int = 3,
        publish: ReplyPublisher | None = None,
    ) -> dict[str, Any]:
        """Process a message with retry logic.

        Args:
            message: The StreamMessage to process
            max_retries: Maximum retry attempts
            publish: Early reply publisher, see process()

        Returns:
            Dict with processing result
        """
        import asyncio

        last_error = None

        for attempt in range(max_retries):
            try:
                return await self.process(message, publish=publish)
            except LockAcquisitionError as e:
                last_error = e
                logger.warning(
                    f"Lock acquisition failed for {message.session_id}, "
                    f"attempt {attempt + 1}/{max_retries}"
                )
                # Exponential backoff
                await asyncio.sleep(0.1 * (2**attempt))
            except Exception as e:
                last_error = e
                logger.error(
                    f"Processing failed for {message.session_id}, "
                    f"attempt {attempt + 1}/{max_retries}: {e}"
                )
                await asyncio.sleep(0.5 * (2**attempt))

        return {
            "session_id": message.session_id,
            "error": str(last_error),
            "success": False,
        }

    async def end_session(self, session_id: str) -> bool:
        """End an interview session and cleanup.

        Args:
            session_id: The session to end

        Returns:
            True if session was cleaned up
        """
        # TODO: generate final evaluation here
        # For now, just delete the context
        deleted = await self.context_manager.delete_context(session_id)
        if deleted:
            logger.info(f"Ended and cleaned up session {session_id}")
        return deleted
