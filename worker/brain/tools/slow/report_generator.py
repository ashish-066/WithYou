"""Report generator tools for slow brain.

Generates two types of reports:
1. Descriptive Report - Narrative summary for human review
2. Analytics Report - Structured data for frontend visualization
"""

import logging
from datetime import datetime, timezone
from typing import Any

from brain.models.llm_pool import get_llm_pool
from brain.models.schemas import (
    AnalyticsReportData,
    DescriptiveReportOutput,
    FilteredToolOutput,
    ReportGenerationInput,
)
from brain.state import InterviewState, VerificationResult

logger = logging.getLogger(__name__)


# =============================================================================
# Prompts
# =============================================================================


DESCRIPTIVE_REPORT_PROMPT = """You are an AI interview analyst generating a comprehensive evaluation report.

Interview Data:
- Candidate ID: {candidate_id}
- Total Turns: {turn_count}
- Topics Covered: {topics_covered}
- Trust Score: {trust_score}
- Integrity Score: {integrity_score}

How the Interview Went:
{interview_completion}

Full Interview Transcript (in order):
{conversation_summary}

Running Scores:
{running_scores}

Verification Results:
{verification_summary}

Timestamp Notes:
{timestamp_notes}

Niche Achievements (OSS Programs, Hackathons, Notable Contributions):
{niche_skills}

Integrity/Proctoring Concerns:
{integrity_concerns}

Generate a detailed evaluation report in JSON format:
{{
    "summary": "2-3 paragraph executive summary",
    "strengths": ["strength1", "strength2", ...],
    "concerns": ["concern1", "concern2", ...],
    "recommendation": "strong_yes|yes|maybe|no|strong_no",
    "recommendation_reasoning": "Brief explanation for the recommendation",
    "detailed_sections": {{
        "Technical Skills": "Assessment of technical abilities...",
        "Communication": "Assessment of communication skills...",
        "Experience": "Assessment of relevant experience...",
        "Cultural Fit": "Assessment of cultural alignment...",
        "Niche Achievements": "Assessment of OSS program participation, hackathon wins, notable contributions...",
        "Integrity Assessment": "Assessment of interview integrity based on proctoring data..."
    }}
}}

Be objective, evidence-based, and cite specific moments from the interview.
Consider niche achievements (GSoC, LFX, hackathon wins) as strong indicators of candidate quality.
If there are significant integrity concerns (low integrity score or multiple flags), factor this into your recommendation.
Be honest about how much evidence there is. If the interview ended early or incomplete (see How the
Interview Went), say so in the first sentence of the summary, assess only what was actually covered,
and do not give "strong_yes" or "strong_no". Name any skills that were not assessed instead of
guessing them. Unanswered questions are evidence too: mention them.
"""


ANALYTICS_REPORT_PROMPT = """You are an AI system generating structured analytics data for interview visualization.

Interview Data:
- Total Turns: {turn_count}
- Topics Covered: {topics_covered}
- Trust Score: {trust_score}
- Integrity Score: {integrity_score}

Running Scores:
{running_scores}

Timestamp Notes:
{timestamp_notes}

Verification Results:
{verification_results}

Integrity Flags:
{integrity_flags}

Generate structured analytics data in JSON format:
{{
    "rubric_scores": {{"technical_depth": 4.2, "problem_solving": 3.8, ...}},
    "skill_distribution": {{"Python": 5, "AWS": 3, ...}},
    "verification_summary": {{"verified": 5, "unverified": 2, "contradiction": 0}},
    "integrity_summary": {{"total_flags": N, "by_type": {{"multiple_faces": 1, ...}}, "by_severity": {{"high": 1, ...}}}},
    "timeline": [
        {{"turn": 1, "event": "topic_intro", "topic": "experience"}},
        {{"turn": 5, "event": "strong_answer", "topic": "technical"}},
        {{"turn": 8, "event": "integrity_flag", "flag_type": "tab_switch"}},
        ...
    ],
    "topic_coverage": {{"experience": 85, "technical": 70, "behavioral": 45}},
    "total_turns": {turn_count}
}}

Use only data from the interview - do not fabricate scores or events.
Include integrity flags in the timeline with event type "integrity_flag".
"""


# =============================================================================
# Descriptive Report Generator
# =============================================================================


async def generate_descriptive_report(
    state: InterviewState,
    input_data: ReportGenerationInput | None = None,
) -> FilteredToolOutput:
    """Generate a narrative evaluation report using the slow brain (Gemini Pro).

    This produces a human-readable report with:
    - Executive summary
    - Strengths and concerns
    - Recommendation with reasoning
    - Detailed section assessments

    Args:
        state: Current interview state
        input_data: Optional configuration for report generation

    Returns:
        FilteredToolOutput containing DescriptiveReportOutput
    """
    try:
        pool = await get_llm_pool()

        # Build prompt data (from the whole interview, not just the last messages)
        prompt_data = _build_report_prompt_data(state, await _load_full_transcript(state))

        prompt = DESCRIPTIVE_REPORT_PROMPT.format(**prompt_data)

        # Generate report
        response_text = await _generate(pool, prompt, max_tokens=2048)

        # Parse response
        report = _parse_descriptive_report(response_text)

        return FilteredToolOutput(
            success=True,
            data=report.model_dump(),
            confidence=0.85,
            source="gemini_pro",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    except Exception as e:
        logger.error(f"Descriptive report generation error: {e}")
        return FilteredToolOutput(
            success=False,
            data=None,
            confidence=0.0,
            source="gemini_pro",
            error=str(e),
            timestamp=datetime.now(timezone.utc).isoformat(),
        )


# =============================================================================
# Analytics Report Generator
# =============================================================================


async def generate_analytics_report(
    state: InterviewState,
    input_data: ReportGenerationInput | None = None,
) -> FilteredToolOutput:
    """Generate structured analytics data for frontend visualization.

    This produces data for:
    - Rubric score charts
    - Skill distribution graphs
    - Verification status breakdown
    - Interview timeline
    - Topic coverage metrics

    Args:
        state: Current interview state
        input_data: Optional configuration for report generation

    Returns:
        FilteredToolOutput containing AnalyticsReportData
    """
    try:
        pool = await get_llm_pool()

        # Build prompt data (this prompt doesn't include the conversation)
        prompt_data = _build_report_prompt_data(state)
        prompt_data["verification_results"] = _format_verification_results(
            state.get("verified_claims", [])
        )

        prompt = ANALYTICS_REPORT_PROMPT.format(**prompt_data)

        # Generate analytics
        response_text = await _generate(pool, prompt, max_tokens=1024)

        # Parse response
        analytics = _parse_analytics_report(response_text, state)

        return FilteredToolOutput(
            success=True,
            data=analytics.model_dump(),
            confidence=0.9,
            source="gemini_pro",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    except Exception as e:
        logger.error(f"Analytics report generation error: {e}")
        # Return fallback analytics with available data
        fallback = _generate_fallback_analytics(state)
        return FilteredToolOutput(
            success=False,
            data=fallback.model_dump(),
            confidence=0.5,
            source="fallback",
            error=str(e),
            timestamp=datetime.now(timezone.utc).isoformat(),
        )


# =============================================================================
# Helper Functions
# =============================================================================


def _format_integrity_concerns(state: InterviewState) -> str:
    """Format integrity/proctoring concerns for the descriptive report prompt.

    Args:
        state: Interview state containing cheat flags

    Returns:
        Formatted string of integrity concerns or 'No concerns detected'
    """
    cheat_flags = state.get("cheat_flags", [])
    integrity_score = state.get("integrity_score", 1.0)

    if not cheat_flags:
        return "No integrity concerns detected during the interview."

    lines = [f"Integrity Score: {integrity_score:.2f}/1.00"]

    # Count by type and severity
    by_type: dict[str, int] = {}
    by_severity: dict[str, int] = {}

    for flag in cheat_flags:
        flag_type = flag.get("flag_type", "unknown")
        severity = flag.get("severity", "medium")
        by_type[flag_type] = by_type.get(flag_type, 0) + 1
        by_severity[severity] = by_severity.get(severity, 0) + 1

    # Summary by severity
    if by_severity:
        severity_parts = []
        for sev in ["critical", "high", "medium", "low"]:
            if by_severity.get(sev, 0) > 0:
                severity_parts.append(f"{by_severity[sev]} {sev}")
        lines.append(f"Flags by severity: {', '.join(severity_parts)}")

    # List specific concerns
    flag_descriptions = {
        "multiple_faces": "Multiple faces detected (possible unauthorized assistance)",
        "phone_detected": "Mobile phone visible (possible answer lookup)",
        "earphone_detected": "Earphone/earbud detected (possible coaching)",
        "tab_switch": "Browser tab switching (possible external resource use)",
        "no_face": "Face not visible",
        "ai_assistance": "Suspected AI-generated response",
        "voice_change": "Voice change detected",
        "suspicious_timing": "Long silence before a long answer (see follow-up checks)",
        "blocked_app": "Blocked app open during the interview",
        "second_screen": "Extra screen connected",
        "app_closed": "App closed before submitting",
        "exit_attempt": "Tried to close the app",
        "emergency_exit": "Emergency exit used",
        "lock_expired": "App lock reached its time limit",
        "browser_mode": "Taken in a browser, without the locked app",
    }

    for flag_type, count in by_type.items():
        desc = flag_descriptions.get(flag_type, flag_type.replace("_", " "))
        lines.append(f"- {desc}: {count} occurrence(s)")

    # Answers that looked looked-up and were tested with a follow-up question
    from brain.verification_probe import report_lines

    checks = report_lines(state)
    if checks:
        lines.append("Follow-up checks (a long silence before a long answer, then a question to test it):")
        lines += checks

    return "\n".join(lines)


def _format_integrity_flags(state: InterviewState) -> str:
    """Format integrity flags for the analytics report prompt.

    Args:
        state: Interview state containing cheat flags

    Returns:
        Formatted string of integrity flags for analytics
    """
    cheat_flags = state.get("cheat_flags", [])

    if not cheat_flags:
        return "No integrity flags recorded."

    lines = [f"Total flags: {len(cheat_flags)}"]

    for flag in cheat_flags[:15]:  # Limit to 15 for prompt
        lines.append(
            f"- Turn {flag.get('turn_number', 0)}: "
            f"{flag.get('flag_type', 'unknown')} "
            f"({flag.get('severity', 'medium')}, "
            f"confidence: {flag.get('confidence', 0):.2f})"
        )

    return "\n".join(lines)


# The report prompt gets the whole conversation, up to these limits (characters).
# A very long interview keeps its opening and as much of the rest as fits.
MAX_MESSAGE_CHARS = 2_000
MAX_CONVERSATION_CHARS = 60_000


async def _load_full_transcript(state: InterviewState) -> list[dict[str, Any]] | None:
    """The full conversation from Redis (state["messages"] holds only the last 10)."""
    session_id = state.get("session_id")
    if not session_id:
        return None
    try:
        from core.redis import get_redis_client
        from services.transcript import load_transcript

        return await load_transcript(await get_redis_client(), session_id)
    except Exception as e:
        logger.warning(f"Report: full transcript unavailable for {session_id}, using recent messages: {e}")
        return None


def _format_conversation(messages: list[dict[str, Any]]) -> str:
    lines = []
    for msg in messages:
        role = msg.get("role")
        if role not in ("user", "human", "assistant"):
            continue
        content = (msg.get("content") or "").strip()
        if not content:
            continue
        if len(content) > MAX_MESSAGE_CHARS:
            content = content[:MAX_MESSAGE_CHARS] + " [...]"
        lines.append(f"{'Interviewer' if role == 'assistant' else 'Candidate'}: {content}")

    if sum(len(line) + 1 for line in lines) <= MAX_CONVERSATION_CHARS:
        return "\n".join(lines) or "No conversation recorded."

    # Too long: keep the opening (a quarter of the budget) and the rest from the end
    head: list[str] = []
    used = 0
    for line in lines:
        if used + len(line) + 1 > MAX_CONVERSATION_CHARS // 4:
            break
        head.append(line)
        used += len(line) + 1
    tail: list[str] = []
    for line in reversed(lines[len(head):]):
        if used + len(line) + 1 > MAX_CONVERSATION_CHARS:
            break
        tail.append(line)
        used += len(line) + 1
    tail.reverse()
    omitted = len(lines) - len(head) - len(tail)
    return "\n".join([*head, f"[... {omitted} messages left out for length ...]", *tail])


def _build_report_prompt_data(
    state: InterviewState, transcript: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    """Build data dictionary for report prompts.

    transcript: the full conversation; without it, the state's recent messages.
    """
    conversation_summary = _format_conversation(transcript or state.get("messages", []))

    # Format running scores
    running_scores = state.get("running_scores", {})
    scores_str = (
        "\n".join([f"- {key}: {value:.1f}/5.0" for key, value in running_scores.items()])
        or "No scores recorded."
    )

    # Format verification summary
    verified_claims = state.get("verified_claims", [])
    verification_counts = {
        "verified": 0,
        "unverified": 0,
        "contradiction": 0,
    }
    for result in verified_claims:
        verdict = result.get("verdict", "unverified")
        if verdict in verification_counts:
            verification_counts[verdict] += 1

    verification_summary = "\n".join(
        [f"- {key}: {count}" for key, count in verification_counts.items()]
    )

    # Format timestamp notes
    timestamp_notes = state.get("timestamp_notes", [])
    notes_str = (
        "\n".join(
            [
                f"- Turn {note.get('turn_number', 0)} [{note.get('tag', 'note')}]: {note.get('content', '')[:100]}"
                for note in timestamp_notes[-10:]  # Last 10 notes
            ]
        )
        or "No notes recorded."
    )

    return {
        "candidate_id": state.get("candidate_id", "unknown"),
        "turn_count": state.get("turn_count", 0),
        "topics_covered": ", ".join(state.get("topics_covered", [])) or "None",
        "trust_score": f"{state.get('trust_score', 1.0):.2f}",
        "integrity_score": f"{state.get('integrity_score', 1.0):.2f}",
        "conversation_summary": conversation_summary,
        "running_scores": scores_str,
        "verification_summary": verification_summary,
        "timestamp_notes": notes_str,
        "interview_completion": _format_completion(state),
        "niche_skills": _format_niche_skills(state),
        "integrity_concerns": _format_integrity_concerns(state),
        "integrity_flags": _format_integrity_flags(state),
    }


async def _generate(pool: Any, prompt: str, max_tokens: int) -> str:
    """The report model, falling back to the interviewer's (faster) model.

    A failed report used to leave the interview without one for good.
    """
    try:
        return await pool.get_slow_client().generate(prompt, max_tokens=max_tokens)
    except Exception as e:
        logger.warning(f"Report model failed ({e}); trying the fast model")
        return await pool.get_fast_client().generate(prompt, max_tokens=max_tokens)


def _format_completion(state: InterviewState) -> str:
    from brain.interview_flow import completion_summary

    c = completion_summary(state)
    lines = [
        f"- Ended because: {c['end_reason']}" + (" (INCOMPLETE interview)" if c["incomplete"] else ""),
        f"- Length: {c['minutes']} minutes",
        f"- Questions left unanswered: {c['unanswered_questions']}",
        f"- Times the candidate was away (out of view or disconnected): {c['absences']}",
    ]
    if c["wrap_up_reason"]:
        lines.append(f"- Wrapped up because: {c['wrap_up_reason'].replace('_', ' ')}")
    if c["skills_not_assessed"]:
        lines.append(f"- Skills with no evidence (not assessed): {', '.join(c['skills_not_assessed'])}")
    return "\n".join(lines)


def _format_niche_skills(state: InterviewState) -> str:
    """Format niche skills for report prompt.

    Args:
        state: Interview state containing candidate profile

    Returns:
        Formatted string of niche achievements or 'None detected'
    """
    profile = state.get("candidate_profile")
    if not profile:
        return "None detected"

    niche = profile.get("niche_skills", {})
    if not niche:
        return "None detected"

    lines = []

    # Format OSS programs
    for program in niche.get("programs", []):
        name = program.get("name", "Unknown program")
        evidence = program.get("evidence", "Unknown source")
        lines.append(f"- OSS Program: {name} (Source: {evidence})")

    # Format hackathon achievements
    for hackathon in niche.get("hackathons", []):
        name = hackathon.get("name", "Unknown achievement")
        lines.append(f"- Hackathon: {name}")

    # Format OSS contributions
    for contrib in niche.get("oss_contributions", []):
        name = contrib.get("name", "Unknown contribution")
        url = contrib.get("url", "")
        if url:
            lines.append(f"- OSS Contribution: {name} ({url})")
        else:
            lines.append(f"- OSS Contribution: {name}")

    return "\n".join(lines) if lines else "None detected"


def _format_verification_results(results: list[VerificationResult]) -> str:
    """Format verification results for prompt."""
    if not results:
        return "No claims verified."

    lines = []
    for result in results[:10]:  # Limit to 10
        claim = result.get("claim", {})
        lines.append(
            f"- Claim: '{claim.get('content', 'unknown')[:50]}' "
            f"→ {result.get('verdict', 'unknown')} "
            f"(confidence: {result.get('confidence', 0):.2f})"
        )

    return "\n".join(lines)


def _parse_descriptive_report(response_text: str) -> DescriptiveReportOutput:
    """Parse LLM response into DescriptiveReportOutput."""
    import json

    try:
        # Clean up response
        text = response_text.strip()
        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]

        data = json.loads(text.strip())

        return DescriptiveReportOutput(
            summary=data.get("summary", "Report generation incomplete."),
            strengths=data.get("strengths", [])[:10],
            concerns=data.get("concerns", [])[:10],
            recommendation=data.get("recommendation", "maybe"),
            recommendation_reasoning=data.get("recommendation_reasoning", ""),
            detailed_sections=data.get("detailed_sections", {}),
        )

    except json.JSONDecodeError:
        logger.warning("Failed to parse descriptive report as JSON")
        return DescriptiveReportOutput(
            summary=response_text[:1000],
            strengths=[],
            concerns=[],
            recommendation="maybe",
            recommendation_reasoning="Report parsing failed",
            detailed_sections={},
        )


def _parse_analytics_report(
    response_text: str,
    state: InterviewState,
) -> AnalyticsReportData:
    """Parse LLM response into AnalyticsReportData."""
    import json

    try:
        # Clean up response
        text = response_text.strip()
        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]

        data = json.loads(text.strip())

        return AnalyticsReportData(
            rubric_scores=data.get("rubric_scores", {}),
            skill_distribution=data.get("skill_distribution", {}),
            verification_summary=data.get(
                "verification_summary",
                {
                    "verified": 0,
                    "unverified": 0,
                    "contradiction": 0,
                },
            ),
            timeline=data.get("timeline", []),
            trust_score=state.get("trust_score", 1.0),
            topic_coverage=data.get("topic_coverage", {}),
            total_turns=state.get("turn_count", 0),
        )

    except json.JSONDecodeError:
        logger.warning("Failed to parse analytics report as JSON, using fallback")
        return _generate_fallback_analytics(state)


def _generate_fallback_analytics(state: InterviewState) -> AnalyticsReportData:
    """Generate fallback analytics from available state data."""
    # Use running scores directly, with niche skills boost applied
    running_scores = dict(state.get("running_scores", {}))

    # Apply niche skills boost to experience_fit
    niche_boost = _calculate_niche_boost(state)
    if niche_boost > 0 and "experience_fit" in running_scores:
        current_score = float(running_scores.get("experience_fit", 0) or 0)
        running_scores["experience_fit"] = min(5.0, current_score + niche_boost)

    # Count verified claims
    verified_claims = state.get("verified_claims", [])
    verification_summary = {
        "verified": 0,
        "unverified": 0,
        "contradiction": 0,
    }
    for result in verified_claims:
        verdict = result.get("verdict", "unverified")
        if verdict in verification_summary:
            verification_summary[verdict] += 1

    # Build timeline from timestamp notes
    timeline = []
    for note in state.get("timestamp_notes", []):
        timeline.append(
            {
                "turn": note.get("turn_number", 0),
                "event": note.get("tag", "note"),
                "content": note.get("content", "")[:50],
            }
        )

    # Calculate topic coverage
    topics_covered = state.get("topics_covered", [])
    turn_count = state.get("turn_count", 1)
    topic_coverage = {
        topic: min(100, (topics_covered.count(topic) / max(turn_count, 1)) * 100)
        for topic in set(topics_covered)
    }

    return AnalyticsReportData(
        rubric_scores=running_scores,
        skill_distribution={},
        verification_summary=verification_summary,
        timeline=timeline,
        trust_score=state.get("trust_score", 1.0),
        topic_coverage=topic_coverage,
        total_turns=turn_count,
    )


def _calculate_niche_boost(state: InterviewState) -> float:
    """Calculate experience_fit score boost from niche skills.

    Args:
        state: Interview state containing candidate profile

    Returns:
        Score boost value (0.0 to 1.0 on 5-point scale)
    """
    profile = state.get("candidate_profile")
    if not profile:
        return 0.0

    niche = profile.get("niche_skills", {})
    if not niche:
        return 0.0

    # Calculate boost: 0.25 per program, 0.15 per hackathon, 0.1 per OSS contribution
    boost = (
        len(niche.get("programs", [])) * 0.25
        + len(niche.get("hackathons", [])) * 0.15
        + len(niche.get("oss_contributions", [])) * 0.1
    )

    return min(boost, 1.0)  # Cap at 1.0 (20% on 5-point scale)
