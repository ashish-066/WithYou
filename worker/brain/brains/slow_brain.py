"""Slow Brain subgraph for deep analysis and report generation.

High-quality processing using Gemini Pro for:
- Profile crawling (GitHub, LinkedIn)
- Claim verification
- Report generation (descriptive and analytics)
- Deep analysis tasks
"""

import logging
from datetime import datetime, timezone
from typing import Any

from langgraph.graph import END, StateGraph

from brain.state import InterviewState, SlowTask, ToolResult, VerificationResult
from brain.tools.slow.profile_crawler import profile_crawler_tool
from brain.tools.slow.report_generator import generate_analytics_report, generate_descriptive_report

logger = logging.getLogger(__name__)


# =============================================================================
# Slow Brain Nodes
# =============================================================================


async def analyze_task_node(state: InterviewState) -> dict[str, Any]:
    """Analyze pending slow tasks and prioritize them.

    This node:
    1. Reviews pending slow tasks
    2. Prioritizes by task type and urgency
    3. Prepares for execution
    """
    session_id = state.get("session_id", "unknown")
    pending_tasks = state.get("pending_slow_tasks", [])

    logger.info(f"[SLOW/ANALYZE] Session {session_id}: {len(pending_tasks)} pending tasks")

    if not pending_tasks:
        # Check for profile crawl initialization
        has_background = (
            state.get("candidate_urls")
            or state.get("candidate_resume_text")
            or state.get("candidate_linkedin_text")
        )
        if state.get("profile_status") == "not_started" and has_background:
            logger.info(f"[SLOW/ANALYZE] Auto-queuing profile crawl for {session_id}")
            pending_tasks = [
                SlowTask(
                    task_id="profile_crawl_init",
                    task_type="profile_crawl",
                    params=state.get("candidate_urls", {}),
                    priority=0,  # Highest priority
                    created_at=datetime.now(timezone.utc).isoformat(),
                )
            ]

        # Check if we should generate reports (interview ended)
        elif state.get("interview_ended") or state.get("input_classification") == "report_request":
            # Queue report generation tasks
            pending_tasks = [
                SlowTask(
                    task_id="report_descriptive",
                    task_type="report_descriptive",
                    params={},
                    priority=1,
                    created_at=datetime.now(timezone.utc).isoformat(),
                ),
                SlowTask(
                    task_id="report_data",
                    task_type="report_data",
                    params={},
                    priority=2,
                    created_at=datetime.now(timezone.utc).isoformat(),
                ),
            ]

    # Sort by priority
    pending_tasks = sorted(pending_tasks, key=lambda x: x.get("priority", 10))

    # Update DFA state
    dfa = state.get("dfa", {})
    if dfa:
        dfa = dict(dfa)
        dfa["current_state"] = "slow_processing"

    return {
        "pending_slow_tasks": pending_tasks,
        "dfa": dfa,
        "last_updated": datetime.now(timezone.utc).isoformat(),
    }


async def execute_slow_tasks_node(state: InterviewState) -> dict[str, Any]:
    """Execute slow brain tasks.

    Processes tasks like:
    - Profile crawling
    - Report generation
    - Deep analysis
    """
    session_id = state.get("session_id", "unknown")
    pending_tasks = state.get("pending_slow_tasks", [])
    completed_tasks = state.get("completed_slow_tasks", []).copy()
    tool_results = state.get("tool_results", []).copy()

    # State updates to accumulate
    updates = {}

    # Track tasks that need to be re-queued (e.g., Hume jobs still processing)
    tasks_to_requeue: list[SlowTask] = []

    for task in pending_tasks:
        if isinstance(task, str):
            task_id = task
            task_type = task
            params = {}
        elif isinstance(task, dict):
            task_id = task.get("task_id", "unknown")
            task_type = task.get("task_type", "")
            params = task.get("params", {}) or {}
        else:
            continue

        logger.info(f"[SLOW/EXECUTE] Session {session_id}: Executing {task_type}")

        try:
            result = None

            if task_type == "profile_crawl":
                updates["profile_status"] = "in_progress"
                # The call sends {"github", "linkedin", "other"}; older callers used *_url
                result = await profile_crawler_tool(
                    github_url=params.get("github") or params.get("github_url"),
                    linkedin_url=params.get("linkedin") or params.get("linkedin_url"),
                    resume_url=params.get("resume_url"),
                    state=state,
                    other_links=params.get("other") or [],
                )
                if result.success:
                    updates["candidate_profile"] = result.data
                    updates["profile_status"] = "completed"
                else:
                    updates["profile_status"] = "failed"

            elif task_type == "report_descriptive":
                result = await generate_descriptive_report(state)
                if result.success:
                    updates["descriptive_report"] = result.data
                    updates["report_status"] = "in_progress"

            elif task_type == "report_data":
                result = await generate_analytics_report(state)
                if result.success:
                    updates["analytics_data"] = result.data
                    # Check if both reports are done
                    if updates.get("descriptive_report") or state.get("descriptive_report"):
                        updates["report_status"] = "completed"

            elif task_type == "deep_analysis":
                # Deep analysis would use slow LLM for thorough evaluation
                result = await _perform_deep_analysis(state, params)

            elif task_type == "verify_claims":
                # Claim verification is handled by verify_claims_node
                # Just mark as complete here, actual verification happens next
                logger.info(
                    f"[SLOW/EXECUTE] Session {session_id}: Claim verification "
                    f"task acknowledged, will verify in next step"
                )
                completed_tasks.append(task_id)
                continue  # Skip result recording, verification happens separately

            elif task_type == "hume_emotional_analysis":
                # Hume.AI emotional analysis
                from brain.tools.slow.hume_analyzer import hume_analyzer_tool

                logger.info(
                    f"[HUME_DEBUG] Processing Hume task for session {session_id}: "
                    f"video_url={params.get('video_url')}, job_id={params.get('job_id')}"
                )

                updates["emotional_analysis_status"] = "processing"
                result = await hume_analyzer_tool(
                    state=state,
                    video_url=params.get("video_url"),
                    job_id=params.get("job_id"),
                )

                if result.success:
                    result_data = result.data

                    # Check if this is job submission or completion
                    if isinstance(result_data, dict) and "status" in result_data:
                        status = result_data["status"]

                        if status in ["QUEUED", "IN_PROGRESS"]:
                            # Still processing - update job_id and re-queue for polling
                            logger.info(
                                f"[HUME_DEBUG] Hume job {result_data.get('job_id')} "
                                f"status: {status} - re-queuing for polling"
                            )
                            # Create updated task with job_id for next poll
                            updated_task = SlowTask(
                                task_id=task_id,
                                task_type="hume_emotional_analysis",
                                params={
                                    "video_url": params.get("video_url"),
                                    "job_id": result_data["job_id"],
                                },
                                priority=task.get("priority", 5),
                                created_at=task.get("created_at", ""),
                            )
                            tasks_to_requeue.append(updated_task)
                            updates["hume_job_id"] = result_data["job_id"]
                            updates["emotional_analysis_status"] = "processing"
                            # Don't mark as complete - will be re-queued
                            continue

                        elif status == "FAILED":
                            updates["emotional_analysis_status"] = "failed"
                            logger.error("[HUME_DEBUG] Hume analysis failed")

                    else:
                        # Analysis complete - save results
                        updates["emotional_analysis"] = result_data
                        updates["emotional_analysis_status"] = "completed"
                        logger.info(
                            f"[HUME_DEBUG] Hume analysis complete: "
                            f"profile={result_data.get('overall_profile')}"
                        )

                        # Note: Emotional analysis is also saved to S3 by avatar service
                        # when it reads the completed state from Redis
                else:
                    updates["emotional_analysis_status"] = "failed"
                    logger.error(f"[HUME_DEBUG] Hume analysis error: {result.error}")

            # -----------------------------------------------------------------
            # DSA Round 2: Evidence extraction + rubric scoring
            # -----------------------------------------------------------------
            elif task_type == "dsa_evaluate":
                # params contains: {"qa_turn": {...}, "problem_id": "..."}
                dsa_state = state.get("dsa_state") or {}
                problem_id = dsa_state.get("problem_id") or params.get("problem_id", "")

                logger.info(
                    f"[DSA/SLOW] Evaluating DSA turn for session {session_id}, "
                    f"problem={problem_id}"
                )
                try:
                    from dsa.tools.slow.dsa_evaluator import evaluate_dsa_turn

                    eval_result = await evaluate_dsa_turn(
                        state=state,
                        params=params,
                    )
                    if eval_result:
                        updates["dsa_state"] = eval_result.get("dsa_state", dsa_state)
                        logger.info(
                            f"[DSA/SLOW] Evaluation complete for {session_id}: "
                            f"scores={eval_result.get('dsa_state', {}).get('scores', {})}"
                        )
                except Exception as e:
                    logger.error(f"[DSA/SLOW] DSA evaluation failed: {e}")

                # DSA evaluation doesn't produce a ToolResult in the normal sense
                completed_tasks.append(task_id)
                continue

            # -----------------------------------------------------------------
            # DSA Round 2: Final report generation
            # -----------------------------------------------------------------
            elif task_type == "dsa_report":
                logger.info(f"[DSA/SLOW] Generating DSA report for session {session_id}")
                try:
                    from dsa.tools.slow.dsa_reporter import generate_dsa_report

                    report_result = await generate_dsa_report(state=state)
                    if report_result:
                        updates["analytics_data"] = report_result  # reuse analytics_data slot
                        updates["report_status"] = "completed"
                        logger.info(f"[DSA/SLOW] DSA report generated for {session_id}")
                except Exception as e:
                    logger.error(f"[DSA/SLOW] DSA report generation failed: {e}")

                completed_tasks.append(task_id)
                continue

            # Record tool result
            if result:
                tool_results.append(
                    ToolResult(
                        tool_name=task_type,
                        input=str(params),
                        output=result.data if result.success else result.error,
                        success=result.success,
                        confidence=result.confidence,
                        source=result.source,
                        timestamp=result.timestamp,
                    )
                )

            completed_tasks.append(task_id)

        except Exception as e:
            logger.error(f"[SLOW/EXECUTE] Task {task_type} failed: {e}")
            tool_results.append(
                ToolResult(
                    tool_name=task_type,
                    input=str(params),
                    output=str(e),
                    success=False,
                    confidence=0.0,
                    source="error",
                    timestamp=datetime.now(timezone.utc).isoformat(),
                )
            )

    # Set pending_slow_tasks to only include tasks that need re-queuing
    updates["pending_slow_tasks"] = tasks_to_requeue
    updates["completed_slow_tasks"] = completed_tasks
    updates["tool_results"] = tool_results

    # If there are tasks to re-queue, schedule a delayed trigger for polling
    if tasks_to_requeue:
        logger.info(
            f"[HUME_DEBUG] {len(tasks_to_requeue)} tasks need re-queuing for session {session_id}"
        )
        # The polling will be triggered by a delayed message published by the worker
        # or by a background task. For now, we rely on the state having pending_slow_tasks
        # which will be picked up on the next graph invocation.
        #
        # To enable automatic polling, we could:
        # 1. Use a Redis delayed queue
        # 2. Publish a delayed message to the stream
        # 3. Use asyncio.create_task with a delay
        #
        # For now, we'll publish a trigger message with a short delay using asyncio
        import asyncio

        async def delayed_trigger():
            await asyncio.sleep(5)  # Wait 5 seconds before polling
            try:
                from core.config import settings
                from core.redis import get_redis_client

                redis = await get_redis_client()
                await redis.xadd(
                    settings.request_stream,
                    {
                        "session_id": session_id,
                        "type": "slow_task_trigger",
                        "content": "poll_hume_status",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                    maxlen=settings.stream_maxlen,
                    approximate=True,
                )
                logger.info(f"[HUME_DEBUG] Published delayed poll trigger for session {session_id}")
                await redis.aclose()
            except Exception as e:
                logger.error(f"[HUME_DEBUG] Failed to publish delayed trigger: {e}")

        asyncio.create_task(delayed_trigger())

    return updates


async def verify_claims_node(state: InterviewState) -> dict[str, Any]:
    """Verify pending claims against candidate profile.

    Cross-references claims from the interview against:
    - GitHub data
    - LinkedIn data
    - Resume data
    """
    session_id = state.get("session_id", "unknown")
    pending_claims = state.get("pending_claims", [])
    verified_claims = state.get("verified_claims", []).copy()
    candidate_profile = state.get("candidate_profile")

    if not pending_claims:
        logger.debug(f"[SLOW/VERIFY] Session {session_id}: No pending claims")
        return {}

    if not candidate_profile:
        logger.warning(f"[SLOW/VERIFY] Session {session_id}: No profile data for verification")
        # Mark claims as unverified (no penalty in trust score)
        for claim in pending_claims:
            verified_claims.append(
                VerificationResult(
                    claim=claim,
                    evidence=[],
                    verdict="unverified",
                    confidence=0.0,
                    reasoning="No candidate profile data available for verification",
                    suggested_followup=None,
                )
            )
        return {
            "pending_claims": [],
            "verified_claims": verified_claims,
        }

    logger.info(f"[SLOW/VERIFY] Session {session_id}: Verifying {len(pending_claims)} claims")

    for claim in pending_claims:
        result = await _verify_single_claim(claim, candidate_profile)
        verified_claims.append(result)

    # Calculate trust score
    trust_score = _calculate_trust_score(verified_claims)

    return {
        "pending_claims": [],
        "verified_claims": verified_claims,
        "trust_score": trust_score,
    }


async def slow_respond_node(state: InterviewState) -> dict[str, Any]:
    """Generate response after slow brain processing.

    This may include acknowledgment of completed tasks or
    report generation confirmation.
    """
    session_id = state.get("session_id", "unknown")
    input_classification = state.get("input_classification", "")

    logger.info(f"[SLOW/RESPOND] Session {session_id}: Generating response")

    # Determine appropriate response based on what was processed
    response = ""

    # Special handling for profile crawl initialization
    if state.get("profile_status") == "completed" and state.get("turn_count", 0) == 0:
        profile = state.get("candidate_profile", {})

        # Construct personalized opening
        response = "Hello! I'm Presence, your AI interviewer today. "

        # Add context from profile if available
        details = []
        if profile.get("github_data") and profile["github_data"].get("name"):
            name = profile["github_data"]["name"]
            response = f"Hello {name}! I'm Presence, your AI interviewer today. "

        if profile.get("skills_extracted"):
            top_skills = profile["skills_extracted"][:3]
            details.append(f"I see you have experience with {', '.join(top_skills)}")

        if profile.get("experience_years"):
            details.append(f"about {profile['experience_years']} years of experience")

        if details:
            response += " ".join(details) + ". "

        response += "I've reviewed your profile and I'm excited to learn more about your background. To start, could you tell me a bit about yourself and what you're looking for in your next role?"

    elif input_classification == "profile_request":
        profile = state.get("candidate_profile")
        if profile:
            response = "I've reviewed the candidate's profile information. "
            if profile.get("github_data"):
                response += f"Found GitHub profile with {profile['github_data'].get('public_repos', 0)} repositories. "
            if profile.get("skills_extracted"):
                skills = profile.get("skills_extracted", [])[:5]
                response += f"Key skills identified: {', '.join(skills)}."
        else:
            response = "I was unable to retrieve the profile information."

    elif input_classification == "report_request":
        report_status = state.get("report_status", "pending")
        if report_status == "completed":
            response = "The interview report has been generated and is ready for review."
        elif report_status == "in_progress":
            response = "Report generation is in progress."
        else:
            response = "I'll generate the interview report now."

    else:
        response = "Analysis complete. How would you like to proceed?"

    # Update DFA state
    dfa = state.get("dfa", {})
    if dfa:
        dfa = dict(dfa)
        dfa["current_state"] = "responding"

    return {
        "response": response,
        "dfa": dfa,
        "last_updated": datetime.now(timezone.utc).isoformat(),
    }


# =============================================================================
# Helper Functions
# =============================================================================


async def _verify_claim_against_niche_skills(
    claim_content: str,
    niche_skills: dict[str, Any],
) -> list[Any]:
    """Verify a claim against niche_skills using semantic LLM matching.

    Checks programs (GSoC, LFX, etc.), hackathons, and OSS contributions
    using Gemini Flash for semantic understanding.

    Args:
        claim_content: The lowercased claim text to verify
        niche_skills: The niche_skills dict from profile

    Returns:
        List of EvidenceMatch objects for matching evidence
    """
    import json
    import re

    from brain.state import EvidenceMatch

    # Collect all evidence items from niche_skills
    evidence_items: list[dict[str, Any]] = []

    for program in niche_skills.get("programs", []):
        evidence_items.append(
            {
                "type": "program",
                "name": program.get("name", ""),
                "evidence": program.get("evidence", ""),
                "confidence": program.get("confidence", 1.0),
            }
        )

    for hackathon in niche_skills.get("hackathons", []):
        evidence_items.append(
            {
                "type": "hackathon",
                "name": hackathon.get("name", ""),
                "evidence": hackathon.get("evidence", ""),
                "confidence": hackathon.get("confidence", 1.0),
            }
        )

    for contrib in niche_skills.get("oss_contributions", []):
        evidence_items.append(
            {
                "type": "oss_contribution",
                "name": contrib.get("name", ""),
                "evidence": contrib.get("evidence", ""),
                "confidence": contrib.get("confidence", 1.0),
            }
        )

    if not evidence_items:
        return []

    # Build prompt for semantic matching
    evidence_list = "\n".join(
        f"{i + 1}. [{e['type']}] {e['name']}: {e['evidence'][:200]}"
        for i, e in enumerate(evidence_items)
    )

    prompt = f"""Determine if the following claim is supported by any of the evidence items.

CLAIM: "{claim_content}"

EVIDENCE ITEMS:
{evidence_list}

Respond with JSON only, no markdown:
{{
  "matches": [
    {{"index": 1, "confidence": 0.95, "reasoning": "Brief explanation"}},
    ...
  ]
}}

Rules:
- Only include matches with confidence >= 0.7
- If no evidence supports the claim, return: {{"matches": []}}
- Match partial claims (e.g., "hackathon winner" matches any hackathon win)
- Be generous with matching - if the claim is reasonably supported, include it
"""

    try:
        from brain.models.llm_pool import get_llm_pool

        pool = await get_llm_pool()
        client = pool.get_fast_client()

        response = await client.generate(prompt, max_tokens=256)

        # Extract JSON from response (handle markdown code blocks)
        json_text = response
        if "```" in response:
            json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", response, re.DOTALL)
            if json_match:
                json_text = json_match.group(1)
        else:
            json_match = re.search(r"\{.*\}", response, re.DOTALL)
            if json_match:
                json_text = json_match.group()

        result = json.loads(json_text)
        matches = result.get("matches", [])

        # Convert to EvidenceMatch objects
        evidence_matches: list[Any] = []
        for match in matches:
            idx = match.get("index", 0) - 1  # Convert to 0-based
            if 0 <= idx < len(evidence_items):
                item = evidence_items[idx]
                match_confidence = match.get("confidence", 0.8)
                evidence_matches.append(
                    EvidenceMatch(
                        source="niche_skills",
                        matched_content=f"[{item['type']}] {item['name']}",
                        relevance_score=match_confidence,
                        match_type="exact" if match_confidence >= 0.85 else "partial",
                    )
                )

        if evidence_matches:
            logger.info(f"[VERIFY] Niche skills matched {len(evidence_matches)} items for claim")

        return evidence_matches

    except Exception as e:
        logger.error(f"[VERIFY] Niche skills semantic matching failed: {e}")
        return []


def _lower(value: object) -> str:
    """Lower-cased text, or "" for missing/None/non-text profile values.

    Profile and resume data come from crawlers, resume parsing and the invite,
    and any field can be present but empty (None). `.get(k, "").lower()` only
    covers a missing key, and crashed the end of an interview on a None.
    """
    return value.lower() if isinstance(value, str) else ""


async def _verify_single_claim(
    claim: dict[str, Any],
    profile: dict[str, Any] | None,
) -> VerificationResult:
    """Verify a single claim against profile data.

    Verdicts:
    - verified: Strong evidence supports the claim (exact match found)
    - unverified: No evidence found, weak evidence, or no profile data
    - contradiction: Evidence explicitly contradicts the claim

    Trust is only penalized for contradictions, not for unverified claims.
    """
    import re

    from brain.state import EvidenceMatch

    claim_content = _lower(claim.get("content"))
    evidence = []
    contradiction_found = False
    contradiction_reason = ""

    # If no profile data, mark as unverified (not penalized in trust score)
    if not profile:
        return VerificationResult(
            claim=claim,
            evidence=[],
            verdict="unverified",
            confidence=0.0,
            reasoning="No candidate profile data available for verification",
            suggested_followup=None,
        )

    # =========================================================================
    # Check GitHub data
    # =========================================================================
    github = profile.get("github") or profile.get("github_data") or {}
    if github:
        # Check for technology/language claims
        languages = [_lower(lang) for lang in (github.get("top_languages") or [])]
        for lang in languages:
            if lang in claim_content:
                evidence.append(
                    EvidenceMatch(
                        source="github",
                        matched_content=f"Found {lang} in top languages",
                        relevance_score=0.8,
                        match_type="partial",
                    )
                )

        # Check for open source contribution claims
        public_repos = github.get("public_repos", 0)
        if "open source" in claim_content or "contributed" in claim_content:
            if public_repos > 10:
                evidence.append(
                    EvidenceMatch(
                        source="github",
                        matched_content=f"Has {public_repos} public repositories",
                        relevance_score=0.7,
                        match_type="partial",
                    )
                )

        # Check bio for keywords
        bio = _lower(github.get("bio"))
        if bio:
            # Check for role keywords in bio
            role_keywords = ["engineer", "developer", "lead", "senior", "architect"]
            for keyword in role_keywords:
                if keyword in claim_content and keyword in bio:
                    evidence.append(
                        EvidenceMatch(
                            source="github",
                            matched_content=f"GitHub bio mentions: {keyword}",
                            relevance_score=0.6,
                            match_type="partial",
                        )
                    )

    # =========================================================================
    # Check LinkedIn data
    # =========================================================================
    linkedin = profile.get("linkedin") or profile.get("linkedin_data") or {}
    if linkedin:
        experience = linkedin.get("experience", [])

        # Check for company claims
        for exp in experience:
            company = _lower(exp.get("company"))
            if company and company in claim_content:
                evidence.append(
                    EvidenceMatch(
                        source="linkedin",
                        matched_content=f"Worked at {company}",
                        relevance_score=0.9,
                        match_type="exact",
                    )
                )

            # Check for job title claims
            title = _lower(exp.get("title"))
            if title:
                # Check exact title match
                if title in claim_content:
                    evidence.append(
                        EvidenceMatch(
                            source="linkedin",
                            matched_content=f"Job title verified: {title}",
                            relevance_score=0.9,
                            match_type="exact",
                        )
                    )
                # Check title keywords (lead, senior, staff, etc.)
                title_keywords = [
                    "lead",
                    "senior",
                    "staff",
                    "principal",
                    "manager",
                    "director",
                ]
                for kw in title_keywords:
                    if kw in claim_content and kw in title:
                        evidence.append(
                            EvidenceMatch(
                                source="linkedin",
                                matched_content=f"Title level '{kw}' verified in: {title}",
                                relevance_score=0.85,
                                match_type="exact",
                            )
                        )
                        break

        # Check for education claims
        education = linkedin.get("education", [])
        for edu in education:
            school = _lower(edu.get("school"))
            degree = _lower(edu.get("degree"))

            # School name verification
            if school and school in claim_content:
                evidence.append(
                    EvidenceMatch(
                        source="linkedin",
                        matched_content=f"Education at {school} verified",
                        relevance_score=0.9,
                        match_type="exact",
                    )
                )

            # Degree verification
            if degree:
                # Check for degree type (BS, MS, PhD, etc.)
                degree_types = ["phd", "masters", "ms ", "bs ", "bachelor", "doctorate"]
                for dt in degree_types:
                    if dt in claim_content and dt in degree:
                        evidence.append(
                            EvidenceMatch(
                                source="linkedin",
                                matched_content=f"Degree type '{dt}' verified",
                                relevance_score=0.85,
                                match_type="exact",
                            )
                        )
                        break

        # Check for publication claims
        publications = linkedin.get("publications", [])
        if publications and ("publish" in claim_content or "paper" in claim_content):
            # Check for specific venue claims
            pubs_lower = [p.lower() if isinstance(p, str) else "" for p in publications]
            venues = ["neurips", "icml", "cvpr", "acl", "emnlp", "iclr"]
            for venue in venues:
                if venue in claim_content:
                    if any(venue in pub for pub in pubs_lower):
                        evidence.append(
                            EvidenceMatch(
                                source="linkedin",
                                matched_content=f"Publication at {venue.upper()} verified",
                                relevance_score=0.95,
                                match_type="exact",
                            )
                        )
                    break

            # Check publication count claims
            pub_count_match = re.search(r"(\d+)\s*paper", claim_content)
            if pub_count_match:
                claimed_pubs = int(pub_count_match.group(1))
                actual_pubs = len(publications)
                if claimed_pubs <= actual_pubs:
                    evidence.append(
                        EvidenceMatch(
                            source="linkedin",
                            matched_content=f"Publication count ({claimed_pubs}) verified",
                            relevance_score=0.9,
                            match_type="exact",
                        )
                    )

    # =========================================================================
    # Check resume data (check both 'resume' and 'resume_data' for compatibility)
    # =========================================================================
    resume = profile.get("resume") or profile.get("resume_data", {})
    if resume:
        logger.debug(
            f"[VERIFY] Checking resume data: skills={len(resume.get('skills', []))}, "
            f"companies={resume.get('companies', [])}, "
            f"certifications={resume.get('certifications', [])}"
        )

        # Check skills (use word boundary matching to avoid false positives)
        skills = [_lower(s) for s in (resume.get("skills") or [])]
        for skill in skills:
            # Use word boundary to avoid "Java" matching "JavaScript"
            if re.search(rf"\b{re.escape(skill)}\b", claim_content, re.IGNORECASE):
                evidence.append(
                    EvidenceMatch(
                        source="resume",
                        matched_content=f"Skill listed: {skill}",
                        relevance_score=0.7,
                        match_type="partial",
                    )
                )

        # Check companies worked at
        companies = [_lower(c) for c in (resume.get("companies") or [])]
        for company in companies:
            if company in claim_content:
                evidence.append(
                    EvidenceMatch(
                        source="resume",
                        matched_content=f"Company verified: {company}",
                        relevance_score=0.9,
                        match_type="exact",
                    )
                )

        # Check detailed work experience entries (experience field contains list of entries)
        experience_entries = resume.get("experience", [])
        for exp in experience_entries:
            if isinstance(exp, dict):
                # Check company name from experience entry
                exp_company = _lower(exp.get("company"))
                if exp_company and exp_company in claim_content:
                    evidence.append(
                        EvidenceMatch(
                            source="resume",
                            matched_content=f"Work experience at {exp_company} verified",
                            relevance_score=0.9,
                            match_type="exact",
                        )
                    )
                # Check job title
                exp_title = _lower(exp.get("title"))
                if exp_title and len(exp_title) > 3:  # Avoid matching short titles
                    # Use word boundary for title matching
                    if re.search(rf"\b{re.escape(exp_title)}\b", claim_content, re.IGNORECASE):
                        evidence.append(
                            EvidenceMatch(
                                source="resume",
                                matched_content=f"Job title '{exp_title}' verified",
                                relevance_score=0.85,
                                match_type="exact",
                            )
                        )

        # Check education - use education_summary if available, else join education list
        education_summary = resume.get("education_summary", "")
        if not education_summary:
            # Fallback: join education list if it's a list
            education_list = resume.get("education", [])
            if isinstance(education_list, list):
                education_summary = " | ".join(str(e) for e in education_list)
            elif isinstance(education_list, str):
                education_summary = education_list
        education = education_summary.lower() if education_summary else ""

        if education:
            # School names
            school_keywords = [
                "stanford",
                "mit",
                "berkeley",
                "carnegie",
                "harvard",
                "university",
                "college",
                "institute",
            ]
            for school in school_keywords:
                if school in claim_content and school in education:
                    evidence.append(
                        EvidenceMatch(
                            source="resume",
                            matched_content=f"Education at {school} verified",
                            relevance_score=0.9,
                            match_type="exact",
                        )
                    )
                    break

        # Check for team size claims - use max_team_size from new schema
        team_size = resume.get("max_team_size") or resume.get("team_size")
        if team_size is not None:
            team_match = re.search(r"team\s+of\s+(\d+)", claim_content)
            if team_match:
                claimed_size = int(team_match.group(1))
                # Verify team size (allow some variance)
                if abs(claimed_size - team_size) <= 2:
                    evidence.append(
                        EvidenceMatch(
                            source="resume",
                            matched_content=f"Team size ~{team_size} verified",
                            relevance_score=0.85,
                            match_type="exact",
                        )
                    )
                elif claimed_size > team_size + 3:
                    # Significant exaggeration of team size
                    contradiction_found = True
                    contradiction_reason = (
                        f"Claims team of {claimed_size}, but profile shows team of {team_size}"
                    )
                    evidence.append(
                        EvidenceMatch(
                            source="resume",
                            matched_content=contradiction_reason,
                            relevance_score=1.0,
                            match_type="none",
                        )
                    )

        # Check for experience year contradictions
        years_match = re.search(r"(\d+)\s*years?", claim_content)
        if years_match:
            claimed_years = int(years_match.group(1))
            profile_years = resume.get("experience_years")
            if profile_years is not None:
                # Allow 1 year tolerance for rounding
                if claimed_years > profile_years + 1:
                    contradiction_found = True
                    contradiction_reason = (
                        f"Claimed {claimed_years} years experience, "
                        f"but profile shows {profile_years} years"
                    )
                    evidence.append(
                        EvidenceMatch(
                            source="resume",
                            matched_content=contradiction_reason,
                            relevance_score=1.0,
                            match_type="none",
                        )
                    )
                elif claimed_years <= profile_years:
                    # Years match or are conservative
                    evidence.append(
                        EvidenceMatch(
                            source="resume",
                            matched_content=f"Experience years ({claimed_years}) verified",
                            relevance_score=0.9,
                            match_type="exact",
                        )
                    )

        # Check for certification claims and contradictions
        certifications = [_lower(c) for c in (resume.get("certifications") or [])]
        cert_checks = [
            ("oscp", "OSCP"),
            ("cka", "CKA"),
            ("ckad", "CKAD"),
            ("aws solutions architect", "AWS Solutions Architect"),
            ("aws certified", "AWS Certified"),
            ("aws security", "AWS Security"),
            ("cissp", "CISSP"),
            ("ceh", "CEH"),
            ("comptia", "CompTIA"),
            ("gcp", "GCP"),
            ("azure", "Azure"),
        ]

        for cert_lower, cert_display in cert_checks:
            if cert_lower in claim_content:
                cert_found = any(cert_lower in c for c in certifications)
                if cert_found:
                    evidence.append(
                        EvidenceMatch(
                            source="resume",
                            matched_content=f"{cert_display} certification verified",
                            relevance_score=0.95,
                            match_type="exact",
                        )
                    )
                elif certifications:
                    # Only contradict if they have OTHER certifications listed
                    # (empty cert list = no data, not contradiction)
                    contradiction_found = True
                    contradiction_reason = (
                        f"Claims {cert_display} certification but not found in profile"
                    )
                    evidence.append(
                        EvidenceMatch(
                            source="resume",
                            matched_content=contradiction_reason,
                            relevance_score=1.0,
                            match_type="none",
                        )
                    )
                break  # Only check first matching cert claim

        # Check for publication count from resume
        resume_pubs = resume.get("publications")
        if resume_pubs is not None:
            pub_match = re.search(r"(\d+)\s*paper", claim_content)
            if pub_match:
                claimed_pubs = int(pub_match.group(1))
                if claimed_pubs <= resume_pubs:
                    evidence.append(
                        EvidenceMatch(
                            source="resume",
                            matched_content=f"Publications ({claimed_pubs}) verified",
                            relevance_score=0.9,
                            match_type="exact",
                        )
                    )
                elif claimed_pubs > resume_pubs + 1:
                    contradiction_found = True
                    contradiction_reason = (
                        f"Claims {claimed_pubs} publications, but profile shows {resume_pubs}"
                    )
                    evidence.append(
                        EvidenceMatch(
                            source="resume",
                            matched_content=contradiction_reason,
                            relevance_score=1.0,
                            match_type="none",
                        )
                    )

    # =========================================================================
    # Check niche_skills data (OSS programs, hackathons, contributions)
    # This uses semantic LLM matching for flexible claim verification
    # =========================================================================
    niche_skills = profile.get("niche_skills", {})
    if niche_skills and claim_content:
        niche_evidence = await _verify_claim_against_niche_skills(claim_content, niche_skills)
        evidence.extend(niche_evidence)

    # =========================================================================
    # Determine verdict based on evidence and contradictions
    # =========================================================================
    if contradiction_found:
        verdict = "contradiction"
        confidence = 0.0  # Contradictions always have 0 confidence
        reasoning = f"Contradiction detected: {contradiction_reason}"
    elif any(e.get("match_type") == "exact" for e in evidence):
        verdict = "verified"
        # Higher confidence with more exact matches
        exact_count = sum(1 for e in evidence if e.get("match_type") == "exact")
        confidence = min(0.95, 0.8 + (exact_count * 0.05))
        reasoning = f"Claim verified with {len(evidence)} evidence matches ({exact_count} exact)"
    elif evidence:
        # Has some evidence but no exact match - still verified if multiple sources
        if len(evidence) >= 2:
            verdict = "verified"
            confidence = 0.7
            reasoning = f"Claim verified with {len(evidence)} supporting evidence items"
        else:
            # Single weak evidence - mark as unverified (no penalty)
            verdict = "unverified"
            confidence = 0.5
            reasoning = "Limited evidence found, cannot conclusively verify"
    else:
        # No evidence at all - unverified (no penalty)
        verdict = "unverified"
        confidence = 0.0
        reasoning = "No matching evidence found in available profile data"

    # Debug logging for claim verification
    claim_preview = (claim.get("content") or "")[:50] if isinstance(claim, dict) else str(claim)[:50]
    logger.info(
        f"[VERIFY] Claim '{claim_preview}...' → {verdict} "
        f"(evidence={len(evidence)}, confidence={confidence:.2f})"
    )
    if evidence:
        for e in evidence[:3]:  # Log first 3 evidence items
            logger.debug(f"[VERIFY]   Evidence: {e.get('source')}: {e.get('matched_content')}")

    return VerificationResult(
        claim=claim,
        evidence=evidence,
        verdict=verdict,
        confidence=confidence,
        reasoning=reasoning,
        suggested_followup=None,
    )


def _calculate_trust_score(verified_claims: list[VerificationResult]) -> float:
    """Calculate aggregate trust score from verification results.

    Trust calculation philosophy: Err on the side of caution.
    - Trust starts at 100% (1.0)
    - Trust is ONLY reduced when a claim is proven to be a CONTRADICTION
    - Unverified claims do NOT reduce trust (absence of evidence != evidence of absence)
    - Each contradiction reduces trust by 15%

    Args:
        verified_claims: List of verification results

    Returns:
        Trust score between 0.0 and 1.0
    """
    if not verified_claims:
        return 1.0  # No claims = full trust

    # Count contradictions
    contradiction_count = sum(1 for r in verified_claims if r.get("verdict") == "contradiction")

    # Each contradiction reduces trust by 15%
    trust_penalty_per_contradiction = 0.15
    trust = 1.0 - (contradiction_count * trust_penalty_per_contradiction)

    # Floor at 0
    return max(0.0, trust)


async def _perform_deep_analysis(
    state: InterviewState,
    params: dict[str, Any],
) -> Any:
    """Perform deep analysis using slow brain LLM."""
    from brain.models.llm_pool import get_llm_pool
    from brain.models.schemas import FilteredToolOutput

    try:
        pool = await get_llm_pool()
        client = pool.get_slow_client()

        prompt = f"""Perform a deep analysis of the interview data.
Analysis focus: {params.get("focus", "overall assessment")}

Interview context:
- Turn count: {state.get("turn_count", 0)}
- Topics: {state.get("topics_covered", [])}
- Trust score: {state.get("trust_score", 1.0)}

Provide a structured analysis."""

        response = await client.generate(prompt, max_tokens=1024)

        return FilteredToolOutput(
            success=True,
            data={"analysis": response},
            confidence=0.8,
            source="gemini_pro",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    except Exception as e:
        from brain.models.schemas import FilteredToolOutput

        return FilteredToolOutput(
            success=False,
            data=None,
            confidence=0.0,
            source="gemini_pro",
            error=str(e),
            timestamp=datetime.now(timezone.utc).isoformat(),
        )


# =============================================================================
# Slow Brain Subgraph
# =============================================================================


def create_slow_brain_subgraph() -> StateGraph:
    """Create the slow brain subgraph for deep analysis.

    Flow:
        analyze -> execute_tasks -> verify_claims -> respond
    """
    graph = StateGraph(InterviewState)

    # Add nodes
    graph.add_node("analyze", analyze_task_node)
    graph.add_node("execute_tasks", execute_slow_tasks_node)
    graph.add_node("verify_claims", verify_claims_node)
    graph.add_node("respond", slow_respond_node)

    # Add edges
    graph.set_entry_point("analyze")
    graph.add_edge("analyze", "execute_tasks")
    graph.add_edge("execute_tasks", "verify_claims")
    graph.add_edge("verify_claims", "respond")
    graph.add_edge("respond", END)

    return graph


async def slow_brain_node(state: InterviewState) -> dict[str, Any]:
    """Single node wrapper for slow brain processing.

    This executes the slow brain subgraph as a single node
    for use in the main dual-brain graph.
    """
    session_id = state.get("session_id", "unknown")
    logger.info(f"[SLOW_BRAIN] Processing session {session_id}")

    try:
        # Execute analyze phase
        analyze_result = await analyze_task_node(state)
        merged_state = {**state, **analyze_result}

        # Execute slow tasks
        tasks_result = await execute_slow_tasks_node(merged_state)
        merged_state = {**merged_state, **tasks_result}

        # Verify claims
        verify_result = await verify_claims_node(merged_state)
        merged_state = {**merged_state, **verify_result}

        # Generate response
        respond_result = await slow_respond_node(merged_state)

        # Merge all results
        final_result = {
            **analyze_result,
            **tasks_result,
            **verify_result,
            **respond_result,
        }

        logger.info(f"[SLOW_BRAIN] Completed session {session_id}")
        return final_result

    except Exception as e:
        logger.error(f"[SLOW_BRAIN] Error in session {session_id}: {e}")
        return {
            "response": "Analysis encountered an error. Please try again.",
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }
