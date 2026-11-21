"""Message processor - orchestrates graph invocation with state management.

This module ties together the state manager, stream manager, and LangGraph
to process interview messages with proper locking and persistence.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any

from redis.asyncio import Redis

from brain import interview_flow, verification_probe
from brain.candidate_background import next_probe
from brain.graph import create_interview_graph
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

            # Handle slow_task_trigger message - process pending slow tasks (e.g., Hume analysis)
            if message.message_type == "slow_task_trigger":
                logger.info(f"[HUME_DEBUG] Received slow_task_trigger for session {session_id}")
                # Force routing to slow brain to process pending tasks
                state["input_classification"] = "slow_task_trigger"
                state["current_input"] = ""  # No actual user input
                # Skip normal processing, just invoke graph to process pending tasks

            # Handle system initialization message for profile crawling
            if message.message_type == "system_init":
                logger.info(f"Initializing profile crawl for session {session_id}")

                raw_data = message.raw_data

                # Extract URLs from message data
                urls = {}
                if "urls" in raw_data:
                    # Depending on how it was sent, it might be a dict or a JSON string
                    import json

                    try:
                        extracted = raw_data["urls"]
                        if isinstance(extracted, str):
                            urls = json.loads(extracted)
                        elif isinstance(extracted, dict):
                            urls = extracted
                    except Exception as e:
                        logger.error(f"Failed to parse URLs: {e}")

                # Extract resume_text from message data
                resume_text = raw_data.get("resume_text")

                # Extract candidate_id if provided (used for ELO tracking)
                candidate_id = raw_data.get("candidate_id")
                if candidate_id:
                    state["candidate_id"] = candidate_id
                    logger.info(f"Set candidate_id for session {session_id}: {candidate_id}")

                # Update state with URLs and reset profile status
                if urls:
                    state["candidate_urls"] = urls
                    state["profile_status"] = "not_started"

                # LinkedIn "Save to PDF" export text (LinkedIn can't be read automatically)
                linkedin_text = raw_data.get("linkedin_text")
                if linkedin_text:
                    state["candidate_linkedin_text"] = linkedin_text
                if resume_text or linkedin_text:
                    # Background to gather even without any links
                    state["profile_status"] = "not_started"
                    state["candidate_urls"] = urls or {}

                # Update state with resume text
                if resume_text:
                    state["candidate_resume_text"] = resume_text
                    logger.info(
                        f"Set candidate_resume_text for session {session_id} "
                        f"({len(resume_text)} chars)"
                    )

                # Handle pre-defined profile data for demo sessions
                # This bypasses the profile crawler and directly sets verification data
                import json as json_module

                demo_profile = {}

                if "github_data" in raw_data:
                    try:
                        github_data = raw_data["github_data"]
                        if isinstance(github_data, str):
                            demo_profile["github_data"] = json_module.loads(github_data)
                        else:
                            demo_profile["github_data"] = github_data
                    except Exception as e:
                        logger.error(f"Failed to parse github_data: {e}")

                if "linkedin_data" in raw_data:
                    try:
                        linkedin_data = raw_data["linkedin_data"]
                        if isinstance(linkedin_data, str):
                            demo_profile["linkedin_data"] = json_module.loads(linkedin_data)
                        else:
                            demo_profile["linkedin_data"] = linkedin_data
                    except Exception as e:
                        logger.error(f"Failed to parse linkedin_data: {e}")

                if "resume_data" in raw_data:
                    try:
                        resume_data = raw_data["resume_data"]
                        if isinstance(resume_data, str):
                            demo_profile["resume_data"] = json_module.loads(resume_data)
                        else:
                            demo_profile["resume_data"] = resume_data
                    except Exception as e:
                        logger.error(f"Failed to parse resume_data: {e}")

                # If we have pre-defined profile data, use it directly
                if demo_profile:
                    state["candidate_profile"] = demo_profile
                    state["profile_status"] = "completed"
                    logger.info(f"Set pre-defined profile data for demo session {session_id}")
                    # For demo sessions with profile data, don't route to slow brain
                    # Just use the fast brain for greeting
                    content = ""
                elif urls or resume_text or linkedin_text:
                    # Force routing to slow brain if we have profile data to crawl
                    state["input_classification"] = "profile_request"
                    content = "System: Start profile crawl"  # Override content for the agent

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

            # Handle DSA Round 2 session initialization
            elif message.message_type == "dsa_init":
                raw_data = message.raw_data
                problem_id = raw_data.get("problem_id", "")
                interview_mode = raw_data.get("interview_mode", "round2_dsa")
                logger.info(
                    f"Initializing DSA interview for session {session_id}, "
                    f"problem_id={problem_id}"
                )

                # Enrich from problem store (auto-load title, expected_concepts, etc.)
                problem_title = raw_data.get("problem_title", "")
                difficulty = raw_data.get("difficulty", "medium")
                expected_concepts: list = list(raw_data.get("expected_concepts", []))
                problem_statement = ""
                ref_algorithm = ""
                ref_time_complexity = ""
                ref_space_complexity = ""

                if problem_id:
                    try:
                        from dsa.problem_store import DSAProblemStore
                        store = DSAProblemStore(self.redis)
                        problem = await store.get(problem_id)
                        if problem:
                            problem_title = problem.title
                            difficulty = problem.difficulty
                            expected_concepts = list(problem.expected_concepts)
                            problem_statement = problem.statement
                            ref_algorithm = problem.reference_solution.algorithm
                            ref_time_complexity = problem.reference_solution.time_complexity
                            ref_space_complexity = problem.reference_solution.space_complexity
                            logger.info(
                                f"Enriched DSA init from store: '{problem_title}' "
                                f"({difficulty}), {len(expected_concepts)} concepts"
                            )
                    except Exception as e:
                        logger.warning(f"Could not load DSA problem '{problem_id}' from store: {e}")

                state["interview_mode"] = interview_mode
                state["dsa_state"] = {
                    "problem_id": problem_id,
                    "problem_title": problem_title,
                    "difficulty": difficulty,
                    "current_approach": None,
                    "proposed_algorithm": None,
                    "candidate_complexity_claim": None,
                    "actual_complexity": None,
                    "demonstrated_concepts": [],
                    "missing_concepts": expected_concepts,
                    "mistakes": [],
                    "optimization_attempts": 0,
                    "reached_optimal": False,
                    "optimization_trigger": None,
                    "current_code": None,
                    "code_language": "python",
                    "code_versions": [],
                    "last_execution_result": None,
                    "matched_solution_class": None,
                    "optimality_gap": None,
                    "current_objective": "understand_problem",
                    "last_action": None,
                    "pending_follow_up": None,
                    "probing_depth": 0,
                    "hints_used": 0,
                    "hint_history": [],
                    "evidence_citations": [],
                    "scores": {},
                    "dsa_turn_count": 0,
                    # Cached reference data (used by reporter + action engine, never shown to candidate)
                    "_problem_statement": problem_statement,
                    "_ref_algorithm": ref_algorithm,
                    "_ref_time_complexity": ref_time_complexity,
                    "_ref_space_complexity": ref_space_complexity,
                    "_initial_approach": "",
                }
                content = ""  # Graph will generate problem introduction

            # Write the report again (it failed, or the recruiter asked to retry)
            elif message.message_type == "regenerate_report":
                return await self._regenerate_report(session_id, state)

            # Proctoring flags from the browser: applied here, under the session
            # lock, so they can't be lost to a concurrent save of the whole state
            elif message.message_type == "proctoring_flags":
                self._apply_proctoring_flags(state, message.raw_data)
                await self.context_manager.update_context(session_id, state)
                if state.get("interview_ended"):
                    await save_interview_outcome(
                        session_id, state, await load_transcript(self.redis, session_id)
                    )
                return {"session_id": session_id, "response": "", "turn_count": state.get("turn_count", 0), "success": True}

            # Silent snapshot of the editor so Presence can see what the candidate is writing
            elif message.message_type == "dsa_code_snapshot":
                code = message.raw_data.get("code", "")
                if state.get("interview_mode") == "round2_dsa" and code:
                    dsa_st = dict(state.get("dsa_state") or {})
                    dsa_st["current_code"] = code
                    state["dsa_state"] = dsa_st
                    await self.context_manager.update_context(session_id, state)
                return {"session_id": session_id, "response": "", "turn_count": state.get("turn_count", 0), "success": True}

            # Handle DSA code execution (candidate clicked "Run Code")
            elif message.message_type == "dsa_code_execute":
                raw_data = message.raw_data
                code = raw_data.get("code", "")
                logger.info(f"Executing DSA code for session {session_id}")

                if code and state.get("interview_mode") == "round2_dsa":
                    try:
                        from dsa.problem_store import DSAProblemStore
                        from sandbox.executor import execute_candidate_code

                        problem_store = DSAProblemStore(self.redis)
                        dsa_st = state.get("dsa_state") or {}
                        problem_id = dsa_st.get("problem_id", "")
                        problem = await problem_store.get(problem_id) if problem_id else None
                        test_cases = problem.public_test_cases if problem else []
                        code_versions = dsa_st.get("code_versions", [])
                        version_num = len(code_versions) + 1

                        exec_result = await execute_candidate_code(
                            code=code,
                            test_cases=test_cases,
                            code_version=version_num,
                            run_hidden=False,
                        )
                        result_dict = exec_result.model_dump()

                        dsa_st["current_code"] = code
                        # last_run: latest run as shown in the editor (incl. runner
                        # outages). last_execution_result / code_versions feed the
                        # interviewer and scoring, and an outage says nothing about
                        # the code, so it isn't recorded there.
                        dsa_st["last_run"] = result_dict
                        if not exec_result.sandbox_unavailable:
                            dsa_st["last_execution_result"] = result_dict
                            code_versions.append({
                                "version": version_num,
                                "code": code,
                                "language": "python",
                                "timestamp": datetime.now(timezone.utc).isoformat(),
                                "execution_result": result_dict,
                            })
                            dsa_st["code_versions"] = code_versions
                        state["dsa_state"] = dsa_st

                        passed = exec_result.tests_passed
                        total = exec_result.tests_total
                        if exec_result.sandbox_unavailable:
                            content = (
                                "[CODE EXECUTION] The code runner is temporarily unavailable, "
                                "so the code was not run. This is not a problem with the "
                                "candidate's code."
                            )
                        elif exec_result.compilation_error:
                            content = f"[CODE EXECUTION] Compilation error: {exec_result.compilation_error[:300]}"
                        elif exec_result.timed_out:
                            content = "[CODE EXECUTION] Code timed out."
                        elif exec_result.runtime_error:
                            content = f"[CODE EXECUTION] Runtime error: {exec_result.runtime_error[:300]}"
                        else:
                            content = (
                                f"[CODE EXECUTION] Tests: {passed}/{total} passed "
                                f"({exec_result.pass_rate*100:.0f}%). "
                                f"Runtime: {exec_result.total_runtime_ms:.1f}ms."
                            )
                        logger.info(f"DSA execution {session_id}: {passed}/{total} passed")
                    except Exception as e:
                        logger.error(f"DSA code execution failed: {e}")
                        content = f"[CODE EXECUTION] Execution failed: {e}"
                else:
                    content = ""

            # Interview progress: time budget, wrap-up, confirming a goodbye,
            # unanswered questions, returns after an absence (brain/interview_flow.py)
            now = datetime.now(timezone.utc)
            decision: interview_flow.Decision | None = None
            probe_started: str | None = None  # flag id of a follow-up check begun this turn
            probe_answered: dict | None = None  # follow-up check answered this turn
            if message.message_type == "candidate_response":
                decision = interview_flow.before_candidate_turn(state, message.content, now)
                state["flow"] = decision.flow
                flow, flag = interview_flow.record_timing(
                    state,
                    _int(message.raw_data.get("response_latency_ms")),
                    message.content,
                    (state.get("turn_count") or 0) + 1,
                    now,
                )
                decision.flow = flow
                if flag:
                    state["cheat_flags"] = [*(state.get("cheat_flags") or []), flag]
                # An answer that looks looked-up is tested with a follow-up
                # (brain/verification_probe.py). This turn is either the answer
                # to such a follow-up, or may start one.
                decision.flow, probe_answered = verification_probe.answered(
                    decision.flow, message.content, _int(message.raw_data.get("response_latency_ms"))
                )
                if (
                    flag
                    and probe_answered is None
                    and decision.action == "continue"
                    and not decision.instruction
                ):
                    decision.flow, decision.instruction = verification_probe.start(
                        decision.flow,
                        flag,
                        message.content,
                        _int(message.raw_data.get("response_latency_ms")) or 0,
                        coding=state.get("interview_mode") == "round2_dsa",
                    )
                    if decision.instruction:
                        probe_started = flag["flag_id"]
            elif message.message_type == "question_unanswered":
                decision = interview_flow.on_unanswered(state)
                content = "[NO ANSWER]"
            elif message.message_type == "candidate_returned":
                decision = interview_flow.on_returned(state)
                content = "[CANDIDATE RETURNED]"
            if decision is not None and message.message_type != "candidate_response":
                # Silence or an absence instead of an answer to the follow-up
                decision.flow, probe_skipped = verification_probe.not_answered(decision.flow)
                if probe_skipped:
                    state["flow"] = decision.flow
                    verification_probe.apply_outcome(
                        state, probe_skipped, "unanswered", probe_skipped["reason"]
                    )
                    decision.flow = state["flow"]
            if decision is not None:
                state["flow"] = decision.flow
                state["interviewer_instruction"] = decision.instruction
                # Ending now: judge the follow-up first, so the report has the verdict
                if probe_answered and decision.action == "conclude":
                    outcome, reason = await verification_probe.judge(probe_answered)
                    verification_probe.apply_outcome(state, probe_answered, outcome, reason)
                    probe_answered = None
                if decision.action == "conclude":
                    state["interview_ended"] = True
                    state["end_reason"] = decision.end_reason
                    state["input_classification"] = "end_signal"

            # A claim the background contradicts or doesn't support: probe it, at
            # most every other turn and never during wrap-up or a goodbye
            state["background_probe"] = ""
            if (
                message.message_type == "candidate_response"
                and decision is not None
                and decision.action == "continue"
                and not decision.instruction
                and (state.get("turn_count") or 0) % 2 == 1
            ):
                probe = next_probe(state)
                if probe:
                    claim_id, guidance = probe
                    flow = dict(state.get("flow") or {})
                    flow["probed_claims"] = [*(flow.get("probed_claims") or []), claim_id]
                    state["flow"] = flow
                    state["background_probe"] = guidance

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

            # The instruction and probe were for this turn only; ratings are tracked for stability
            result["interviewer_instruction"] = ""
            result["background_probe"] = ""
            if message.message_type == "candidate_response" and not result.get("interview_ended"):
                result["flow"] = interview_flow.record_levels(result)

            # Follow-up checks: keep the question that was asked; judge an answer.
            # The reply has already been sent, so this costs the candidate no time.
            if probe_started:
                result["flow"] = verification_probe.set_question(
                    result.get("flow") or {}, probe_started, result.get("response") or ""
                )
            if probe_answered:
                outcome, reason = await verification_probe.judge(probe_answered)
                verification_probe.apply_outcome(result, probe_answered, outcome, reason)
                logger.info(f"Follow-up check for {session_id} turn {probe_answered.get('turn')}: {outcome}")

            # Save updated context
            await self.context_manager.update_context(session_id, result)

            # Full transcript (state keeps only the last few messages)
            turn = result.get("turn_count")
            reply = result.get("response") or ""
            # A reply carried over unchanged in state (no node answered) isn't new
            is_new = message.message_type == "candidate_response" or reply != previous_reply
            if isinstance(reply, str) and reply.strip() and is_new:
                await append_message(self.redis, session_id, "assistant", reply, turn)

            # Ended interviews: copy the outcome to Postgres (re-saved when later
            # steps, e.g. the DSA report, add to it)
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
            if not state.get("analytics_data") and state.get("interview_mode") != "round2_dsa":
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

    @staticmethod
    def _apply_proctoring_flags(state: dict, raw_data: dict) -> None:
        """Append new flags/timeline notes (skipping already-applied flag ids)
        and recompute the integrity score."""
        from services.anti_cheat import anti_cheat_service

        def parse(field: str) -> list:
            value = raw_data.get(field) or "[]"
            try:
                parsed = json.loads(value) if isinstance(value, str) else value
            except json.JSONDecodeError:
                return []
            return parsed if isinstance(parsed, list) else []

        flags = list(state.get("cheat_flags") or [])
        notes = list(state.get("timestamp_notes") or [])
        seen = {f.get("id") for f in flags}
        for flag, note in zip(parse("flags"), parse("notes")):
            if flag.get("id") in seen:
                continue  # redelivered message
            seen.add(flag.get("id"))
            flags.append(flag)
            notes.append(note)

        state["cheat_flags"] = flags
        state["timestamp_notes"] = notes
        state["integrity_score"] = anti_cheat_service.calculate_integrity_score(flags)

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
