"""DSA Report Generator — generates the final evidence-backed DSA report.

Called by the slow brain as a 'dsa_report' slow task at the end of a
Round 2 DSA interview. Produces a DSAFinalReport with:
- Code execution results (authoritative)
- Evidence citations per rubric dimension
- Weighted final score
- Strengths / weaknesses / recommendation

The LLM generates ONLY the narrative sections (strengths, weaknesses,
narrative_summary). All numeric scores come from code execution + evidence.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from brain.state import InterviewState
from dsa.models import DSAFinalReport

logger = logging.getLogger(__name__)


# =============================================================================
# Narrative generation prompt
# =============================================================================

DSA_NARRATIVE_PROMPT = """You are generating the narrative sections of a DSA interview assessment report.

<candidate_performance>
Problem: {problem_title} ({difficulty})
Algorithm Used: {algorithm_classification} ({solution_class})
Code Correctness: {tests_passed}/{tests_total} tests passed
Complexity Claimed: {complexity_claimed}
Hints Used: {hints_used}
Mistakes Made: {mistakes_count}
Mistakes Self-Corrected: {self_corrected}
Reached Optimal: {reached_optimal}
Dimension Scores: {dimension_scores}
</candidate_performance>

<evidence_citations>
{evidence_summary}
</evidence_citations>

Generate ONLY this JSON object — no markdown, no extra text:
{{
  "strengths": ["<3-5 specific strength bullets based on evidence>"],
  "weaknesses": ["<2-4 specific weakness bullets based on evidence>"],
  "narrative_summary": "<2-3 sentence balanced summary of the candidate's performance>",
  "recommendation": "<strong_yes | yes | maybe | no | strong_no>"
}}

Base recommendation on:
- strong_yes: >85% weighted score, optimal solution, clean code, excellent communication
- yes: 70-85% score, near-optimal, good reasoning, minor gaps
- maybe: 50-70% score, correct but suboptimal, some communication issues
- no: 30-50% score, significant gaps in correctness or reasoning
- strong_no: <30% score, fundamental misunderstanding or could not code
"""


# =============================================================================
# Score calculations
# =============================================================================

DIMENSION_WEIGHTS = {
    "problem_understanding": 0.10,
    "algorithm_selection": 0.20,
    "reasoning": 0.20,
    "code_correctness": 0.20,
    "complexity_analysis": 0.10,
    "edge_case_handling": 0.10,
    "optimization": 0.05,
    "communication": 0.05,
}


def _compute_weighted_score(scores: dict[str, float]) -> float:
    """Compute weighted average score across all dimensions."""
    total = 0.0
    weight_used = 0.0
    for dim, weight in DIMENSION_WEIGHTS.items():
        if dim in scores:
            total += scores[dim] * weight
            weight_used += weight
    if weight_used == 0:
        return 0.0
    # Normalize to account for missing dimensions
    return total / weight_used if weight_used < 1.0 else total


def _code_correctness_from_execution(dsa_state: dict[str, Any]) -> float:
    """Derive code_correctness score from execution result (authoritative)."""
    last_result = dsa_state.get("last_execution_result")
    if not last_result:
        return 0.0  # No code submitted
    if last_result.get("compilation_error"):
        return 0.0
    if last_result.get("timed_out"):
        return 0.1  # Slight credit for compiling
    return float(last_result.get("pass_rate", 0.0))


# =============================================================================
# Main report generator
# =============================================================================

async def generate_dsa_report(state: InterviewState) -> dict[str, Any] | None:
    """Generate the final DSA interview report.

    Called at the end of a Round 2 DSA interview.

    Returns:
        dict with the full report as serializable data, or None on failure.
    """
    session_id = state.get("session_id", "unknown")
    dsa_state = dict(state.get("dsa_state") or {})

    if not dsa_state:
        logger.error(f"[DSA/REPORTER] No DSA state found for session {session_id}")
        return None

    # ----- Gather data -----
    problem_title = dsa_state.get("problem_title", "Unknown")
    difficulty = dsa_state.get("difficulty", "medium")
    solution_class = dsa_state.get("matched_solution_class") or "incorrect"
    proposed_algorithm = dsa_state.get("proposed_algorithm", "Unknown")

    last_result = dsa_state.get("last_execution_result") or {}
    tests_passed = last_result.get("tests_passed", 0)
    tests_total = last_result.get("tests_total", 0)
    pass_rate = last_result.get("pass_rate", 0.0)
    runtime_ms = last_result.get("total_runtime_ms", 0.0)
    compilation_error = last_result.get("compilation_error", "") or None
    runtime_error = last_result.get("runtime_error", "") or None

    mistakes = dsa_state.get("mistakes", [])
    self_corrected = sum(1 for m in mistakes if m.get("corrected"))
    hints_used = dsa_state.get("hints_used", 0)
    reached_optimal = dsa_state.get("reached_optimal", False)

    # Override code_correctness with authoritative execution score
    scores = dict(dsa_state.get("scores", {}))
    scores["code_correctness"] = _code_correctness_from_execution(dsa_state)

    # Compute weighted final score
    final_score = _compute_weighted_score(scores)

    # Build evidence summary for narrative
    citations = dsa_state.get("evidence_citations", [])
    evidence_summary = "\n".join(
        f"- [{c.get('dimension')}] {c.get('verdict')}: {c.get('evidence', 'N/A')}"
        for c in citations[:15]  # Limit to keep prompt short
    ) or "No evidence recorded."

    # ----- LLM narrative call -----
    prompt = DSA_NARRATIVE_PROMPT.format(
        problem_title=problem_title,
        difficulty=difficulty,
        algorithm_classification=proposed_algorithm,
        solution_class=solution_class,
        tests_passed=tests_passed,
        tests_total=tests_total,
        complexity_claimed=dsa_state.get("candidate_complexity_claim", "Not stated"),
        hints_used=hints_used,
        mistakes_count=len(mistakes),
        self_corrected=self_corrected,
        reached_optimal=reached_optimal,
        dimension_scores=", ".join(f"{k}: {v:.2f}" for k, v in scores.items()),
        evidence_summary=evidence_summary,
    )

    try:
        import json

        from brain.models.llm_pool import get_llm_pool
        pool = await get_llm_pool()
        raw_text = str(await pool.get_slow_client().generate(prompt)).strip()
        if raw_text.startswith("```"):
            raw_text = raw_text.split("```")[1]
            if raw_text.startswith("json"):
                raw_text = raw_text[4:]
        raw_text = raw_text.strip()
        narrative = json.loads(raw_text)
    except Exception as e:
        logger.error(f"[DSA/REPORTER] Narrative generation failed: {e}")
        narrative = {
            "strengths": ["Unable to generate narrative"],
            "weaknesses": [],
            "narrative_summary": "Report generation encountered an error.",
            "recommendation": "maybe",
        }

    # ----- Build final report -----
    report = DSAFinalReport(
        session_id=session_id,
        problem_id=dsa_state.get("problem_id", "unknown"),
        problem_title=problem_title,
        difficulty=difficulty,  # type: ignore
        generated_at=datetime.now(timezone.utc).isoformat(),
        initial_approach=dsa_state.get("_initial_approach", ""),
        final_approach=dsa_state.get("current_approach", ""),
        algorithm_classification=solution_class,  # type: ignore
        optimality_gap=dsa_state.get("optimality_gap"),
        code_submitted=bool(dsa_state.get("current_code")),
        final_code=dsa_state.get("current_code"),
        tests_passed=tests_passed,
        tests_total=tests_total,
        pass_rate=pass_rate,
        runtime_ms=runtime_ms,
        compilation_error=compilation_error,
        runtime_error=runtime_error,
        candidate_time_complexity=dsa_state.get("candidate_complexity_claim"),
        candidate_space_complexity=None,
        reference_time_complexity=dsa_state.get("_ref_time_complexity", "O(?)"),
        reference_space_complexity=dsa_state.get("_ref_space_complexity", "O(?)"),
        mistakes=mistakes,
        recovery_summary=f"{self_corrected}/{len(mistakes)} mistakes self-corrected",
        hints_used=hints_used,
        optimization_behavior=(
            "Reached optimal solution" if reached_optimal
            else f"Did not reach optimal ({dsa_state.get('optimality_gap', 'gap unknown')})"
        ),
        dimension_scores=scores,
        final_weighted_score=final_score,
        final_score_percentage=round(final_score * 100, 1),
        evidence_citations=citations,
        elo_rating=None,   # Set by Elo system after comparison
        elo_percentile=None,
        strengths=narrative.get("strengths", []),
        weaknesses=narrative.get("weaknesses", []),
        recommendation=narrative.get("recommendation", "maybe"),  # type: ignore
        narrative_summary=narrative.get("narrative_summary", ""),
    )

    logger.info(
        f"[DSA/REPORTER] Report generated for {session_id}: "
        f"score={final_score:.2f}, recommendation={report.recommendation}"
    )

    return report.model_dump()
