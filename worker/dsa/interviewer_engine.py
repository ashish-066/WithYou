"""DSA Interviewer Engine — constrained action selection.

This module decides WHAT Presence should do next based on the current
DSA interview state. It is NOT a free-form LLM call — the action
set is fixed and the selection logic is deterministic + evidence-driven.

The LLM is only invoked to GENERATE the natural language phrasing
of the selected action, not to decide which action to take.

Architecture:
    select_next_action(dsa_state, problem) -> InterviewerAction
    generate_action_text(action, dsa_state, problem) -> str (LLM call)
"""

from __future__ import annotations

import logging
from typing import Any

from dsa.models import (
    DSAProblem,
    InterviewerAction,
    SolutionClass,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Action Selection Logic (Deterministic)
# =============================================================================


def select_next_action(
    dsa_state: dict[str, Any],
    problem: DSAProblem,
) -> InterviewerAction:
    """Select the best next interviewer action based on current DSA state.

    This is DETERMINISTIC and rule-based — not a free LLM call.
    The rules encode expert interviewer judgment about when to:
    - Probe deeper vs move forward
    - Challenge vs accept
    - Ask for code vs continue discussion
    - Give a hint vs wait
    - End the interview

    Args:
        dsa_state: Current DSAInterviewState dict
        problem: The DSAProblem being evaluated

    Returns:
        The selected InterviewerAction literal
    """
    dsa_turn = dsa_state.get("dsa_turn_count", 0)
    scores = dsa_state.get("scores", {})
    current_approach = dsa_state.get("current_approach")
    matched_class = dsa_state.get("matched_solution_class")
    current_code = dsa_state.get("current_code")
    last_action = dsa_state.get("last_action")
    last_result = dsa_state.get("last_execution_result")
    missing = set(dsa_state.get("missing_concepts", []))
    hints_used = dsa_state.get("hints_used", 0)
    optimization_attempts = dsa_state.get("optimization_attempts", 0)
    reached_optimal = dsa_state.get("reached_optimal", False)
    probing_depth = dsa_state.get("probing_depth", 0)

    rubric = problem.scoring_rubric
    max_hints = problem.hint_policy.max_hints
    hints_allowed = problem.hint_policy.allowed

    # --- Score shorthands ---
    complexity_score = scores.get("complexity_analysis", -1.0)
    algorithm_score = scores.get("algorithm_selection", -1.0)
    edge_case_score = scores.get("edge_case_handling", -1.0)

    # -------------------------------------------------------------------------
    # Rule 1: End if we've been going too long
    # -------------------------------------------------------------------------
    max_turns = 25  # hard ceiling
    if dsa_turn >= max_turns:
        return "END_INTERVIEW"

    # -------------------------------------------------------------------------
    # Rule 2: If no approach has been described yet, ask for clarification
    # -------------------------------------------------------------------------
    if not current_approach and dsa_turn < 3:
        return "ASK_CLARIFICATION"

    # -------------------------------------------------------------------------
    # Rule 3: After approach is described but no complexity asked yet
    # -------------------------------------------------------------------------
    if current_approach and complexity_score < 0 and last_action not in (
        "ASK_COMPLEXITY", "CHALLENGE_ASSUMPTION"
    ):
        return "ASK_COMPLEXITY"

    # -------------------------------------------------------------------------
    # Rule 4: If algorithm not classified yet (still "incorrect" or None)
    #         and candidate gave no explanation of WHY
    # -------------------------------------------------------------------------
    if algorithm_score < 0 and last_action not in ("ASK_WHY", "ASK_CLARIFICATION"):
        return "ASK_WHY"

    # -------------------------------------------------------------------------
    # Rule 5: Challenge wrong complexity claim
    # -------------------------------------------------------------------------
    if (
        complexity_score is not None
        and complexity_score < 0.3
        and probing_depth < 2
        and last_action != "CHALLENGE_ASSUMPTION"
    ):
        return "CHALLENGE_ASSUMPTION"

    # -------------------------------------------------------------------------
    # Rule 6: Ask for edge cases if not demonstrated and high weight
    # -------------------------------------------------------------------------
    edge_weight = rubric.get_weight("edge_case_handling")
    if (
        edge_case_score < 0
        and edge_weight >= 0.08
        and dsa_turn >= 3
        and last_action not in ("ASK_EDGE_CASE", "ASK_EXAMPLE")
    ):
        return "ASK_EDGE_CASE"

    # -------------------------------------------------------------------------
    # Rule 7: Request code if we have enough understanding
    # -------------------------------------------------------------------------
    if (
        not current_code
        and current_approach
        and dsa_turn >= 3
        and last_action not in ("REQUEST_CODE",)
    ):
        return "REQUEST_CODE"

    # -------------------------------------------------------------------------
    # Rule 8: If code was submitted and we have execution results
    # -------------------------------------------------------------------------
    if current_code and last_result:
        pass_rate = last_result.get("pass_rate", 0.0)
        timed_out = last_result.get("timed_out", False)
        compilation_error = last_result.get("compilation_error", "")
        runtime_error = last_result.get("runtime_error", "")

        # There's a failure to discuss
        if (
            pass_rate < 1.0 or timed_out or compilation_error or runtime_error
        ) and last_action not in ("DISCUSS_FAILURE",):
            return "DISCUSS_FAILURE"

    # -------------------------------------------------------------------------
    # Rule 9: Ask for optimization if:
    #   - Solution is suboptimal (not optimal/alternative)
    #   - We haven't probed optimization yet
    #   - Optimization has significant weight in rubric
    # -------------------------------------------------------------------------
    opt_weight = rubric.get_weight("optimization")
    if (
        matched_class in ("suboptimal_valid", "incorrect")
        and optimization_attempts == 0
        and opt_weight >= 0.05
        and not reached_optimal
        and last_action not in ("ASK_OPTIMIZATION", "PROVIDE_HINT")
    ):
        return "ASK_OPTIMIZATION"

    # -------------------------------------------------------------------------
    # Rule 10: If candidate tried optimization and failed → hint if allowed
    # -------------------------------------------------------------------------
    if (
        optimization_attempts >= 1
        and not reached_optimal
        and hints_allowed
        and hints_used < max_hints
        and last_action == "ASK_OPTIMIZATION"
    ):
        return "PROVIDE_HINT"

    # -------------------------------------------------------------------------
    # Rule 11: If everything important is demonstrated, move forward or end
    # -------------------------------------------------------------------------
    all_evidence_collected = (
        complexity_score >= 0
        and algorithm_score >= 0
        and edge_case_score >= 0
        and (current_code is not None)
    )

    if all_evidence_collected and dsa_turn >= 8:
        # Check if there are any important missing concepts still
        if missing and probing_depth < 2:
            return "ASK_EDGE_CASE"  # One more probe
        return "END_INTERVIEW"

    # -------------------------------------------------------------------------
    # Rule 12: Default — move forward with next topic
    # -------------------------------------------------------------------------
    if last_action in ("DISCUSS_FAILURE", "ASK_OPTIMIZATION", "PROVIDE_HINT"):
        return "MOVE_FORWARD"

    # Final fallback
    return "ASK_CLARIFICATION"


# =============================================================================
# Evidence sufficiency check
# =============================================================================


def has_sufficient_evidence(
    dsa_state: dict[str, Any],
    rubric_weight_threshold: float = 0.08,
) -> bool:
    """Return True if enough evidence has been gathered to stop probing.

    Used to prevent the interviewer from asking endless follow-up questions
    once the candidate has demonstrated mastery (or lack thereof) of a topic.
    """
    scores = dsa_state.get("scores", {})
    required_dimensions = [
        "problem_understanding",
        "algorithm_selection",
        "reasoning",
        "complexity_analysis",
    ]
    # All required dimensions must have been assessed (score >= 0)
    return all(scores.get(dim, -1.0) >= 0 for dim in required_dimensions)


# =============================================================================
# Solution classification
# =============================================================================


def classify_solution(
    candidate_algorithm: str | None,
    problem: DSAProblem,
) -> SolutionClass:
    """Classify the candidate's approach against the problem's solution landscape.

    Returns:
        "optimal" | "acceptable_alternative" | "suboptimal_valid" | "incorrect"
    """
    if not candidate_algorithm:
        return "incorrect"

    algo_lower = candidate_algorithm.lower()

    # Check reference solution
    ref_algo = problem.reference_solution.algorithm.lower()
    if algo_lower in ref_algo or ref_algo in algo_lower:
        return "optimal"

    # Check acceptable alternatives
    for alt in problem.acceptable_alternatives:
        if algo_lower in alt.algorithm.lower() or alt.algorithm.lower() in algo_lower:
            return "acceptable_alternative"

    # Check suboptimal valid
    for sub in problem.suboptimal_valid:
        if algo_lower in sub.algorithm.lower() or sub.algorithm.lower() in algo_lower:
            return "suboptimal_valid"

    return "incorrect"


# =============================================================================
# Optimality gap
# =============================================================================


def compute_optimality_gap(
    solution_class: SolutionClass,
    problem: DSAProblem,
    candidate_complexity: str | None = None,
) -> str | None:
    """Return a human-readable description of the gap vs optimal."""
    if solution_class == "optimal":
        return None  # No gap

    ref = problem.reference_solution
    ref_desc = f"{ref.algorithm} ({ref.time_complexity} time, {ref.space_complexity} space)"

    if solution_class == "acceptable_alternative":
        return f"Valid alternative approach. Optimal is {ref_desc}."

    if solution_class == "suboptimal_valid":
        if candidate_complexity:
            return (
                f"Correct but suboptimal: {candidate_complexity}. "
                f"Optimal is {ref_desc}."
            )
        return f"Correct but suboptimal. Optimal is {ref_desc}."

    # incorrect
    return f"Approach does not solve the problem correctly. Optimal is {ref_desc}."
