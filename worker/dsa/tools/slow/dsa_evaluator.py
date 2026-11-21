"""DSA Evidence Extractor — slow brain constrained LLM evaluation.

Extracts evidence citations from the most recent DSA Q&A exchange
and updates the rubric scores in dsa_state.

Follows the same constrained LLM pattern as scoring/evidence_extractor.py:
- Fixed JSON schema output (no free prose)
- Verbatim quotes from transcript required
- Confidence must be stated
- LLM is NOT the source of truth for code correctness
  (code_correctness score comes from ExecutionResult, not LLM)
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from brain.state import InterviewState

logger = logging.getLogger(__name__)


# =============================================================================
# Constrained evidence extraction prompt
# =============================================================================

DSA_EVIDENCE_PROMPT = """You are evaluating a candidate's DSA interview turn for evidence of competency.

<problem>
{problem_context}
</problem>

<latest_exchange>
Interviewer: {interviewer_question}
Candidate: {candidate_response}
</latest_exchange>

<current_approach>
{current_approach}
</current_approach>

Evaluate the candidate's response for evidence on each dimension listed below.
Output ONLY a JSON object with this exact schema — no explanation, no markdown:

{{
  "evidence": [
    {{
      "dimension": "<one of: problem_understanding | algorithm_selection | reasoning | complexity_analysis | edge_case_handling | optimization | communication>",
      "criterion": "<specific criterion being evaluated>",
      "verdict": "<Yes | No | Insufficient>",
      "evidence": "<exact verbatim quote from candidate response, or N/A>",
      "confidence": <0.0-1.0>,
      "reasoning": "<one sentence>"
    }}
  ],
  "proposed_algorithm": "<algorithm name if identifiable, else null>",
  "candidate_complexity_claim": "<e.g. O(n) if stated, else null>",
  "demonstrated_concepts": ["<concept1>", "<concept2>"],
  "new_mistakes": [
    {{
      "description": "<what the mistake was>",
      "mistake_type": "<wrong_algorithm|wrong_complexity|wrong_edge_case|wrong_assumption|bug_in_code|other>"
    }}
  ]
}}

IMPORTANT:
- code_correctness MUST NOT be set here — it is set by execution results only.
- evidence must be a verbatim quote from <latest_exchange>, not a paraphrase.
- If there is no evidence for a dimension in this turn, omit it from the list.
- Only assess dimensions that have CLEAR evidence in this specific turn.
"""


# =============================================================================
# Score update from verdicts
# =============================================================================

def _update_scores_from_evidence(
    existing_scores: dict[str, float],
    evidence_list: list[dict[str, Any]],
) -> dict[str, float]:
    """Update rubric scores from new evidence. Uses exponential moving average."""
    scores = dict(existing_scores)
    VERDICT_MAP = {"Yes": 1.0, "No": 0.0, "Insufficient": 0.4}  # noqa: N806
    EMA_ALPHA = 0.6  # Weight for new evidence vs historical  # noqa: N806

    for ev in evidence_list:
        dim = ev.get("dimension", "")
        verdict = ev.get("verdict", "Insufficient")
        confidence = float(ev.get("confidence", 0.5))
        raw_score = VERDICT_MAP.get(verdict, 0.4) * confidence

        if dim in scores:
            # Blend with existing score (exponential moving average)
            scores[dim] = EMA_ALPHA * raw_score + (1 - EMA_ALPHA) * scores[dim]
        else:
            scores[dim] = raw_score

    return scores


# =============================================================================
# Main evaluation function
# =============================================================================

async def evaluate_dsa_turn(
    state: InterviewState,
    params: dict[str, Any],
) -> dict[str, Any] | None:
    """Extract DSA evidence from the latest Q&A turn and update dsa_state.

    Called by the slow brain as a 'dsa_evaluate' slow task.

    IMPORTANT: code_correctness is NOT set by this function.
    It is set by the sandbox executor's ExecutionResult.

    Returns:
        Partial state update with updated dsa_state, or None on failure.
    """
    dsa_state = dict(state.get("dsa_state") or {})
    messages = state.get("messages", [])

    # Get last interviewer + candidate exchange
    if len(messages) < 2:
        logger.warning("[DSA/EVALUATOR] Not enough messages to evaluate")
        return None

    # Find the most recent human response and preceding AI question
    candidate_response = ""
    interviewer_question = ""
    for msg in reversed(messages):
        role = msg.get("role", "")
        content = msg.get("content", "")
        if role in ("human", "user") and not candidate_response:
            candidate_response = content
        elif role == "assistant" and candidate_response and not interviewer_question:
            interviewer_question = content
            break

    if not candidate_response:
        return None

    # Build problem context
    problem_title = dsa_state.get("problem_title", "Unknown")
    difficulty = dsa_state.get("difficulty", "medium")
    current_approach = dsa_state.get("current_approach", "Not yet described")
    problem_context = f"Title: {problem_title}\nDifficulty: {difficulty}"

    prompt = DSA_EVIDENCE_PROMPT.format(
        problem_context=problem_context,
        interviewer_question=interviewer_question or "(No question)",
        candidate_response=candidate_response,
        current_approach=current_approach,
    )

    # LLM call (constrained JSON output)
    try:
        from brain.models.llm_pool import get_llm_pool
        pool = await get_llm_pool()
        raw_text = str(await pool.get_slow_client().generate(prompt)).strip()

        # Strip markdown fences if present
        if raw_text.startswith("```"):
            raw_text = raw_text.split("```")[1]
            if raw_text.startswith("json"):
                raw_text = raw_text[4:]
        raw_text = raw_text.strip()

        parsed = json.loads(raw_text)
    except Exception as e:
        logger.error(f"[DSA/EVALUATOR] LLM extraction failed: {e}")
        return None

    # Extract fields
    evidence_list = parsed.get("evidence", [])
    proposed_algorithm = parsed.get("proposed_algorithm")
    complexity_claim = parsed.get("candidate_complexity_claim")
    new_concepts = parsed.get("demonstrated_concepts", [])
    new_mistakes = parsed.get("new_mistakes", [])

    # Update dsa_state
    existing_citations = dsa_state.get("evidence_citations", [])
    for ev in evidence_list:
        ev["turn_number"] = dsa_state.get("dsa_turn_count", 0)
        ev["timestamp"] = datetime.now(timezone.utc).isoformat()
        existing_citations.append(ev)

    # Update proposed algorithm if found
    if proposed_algorithm:
        dsa_state["proposed_algorithm"] = proposed_algorithm

    # Update complexity claim
    if complexity_claim:
        dsa_state["candidate_complexity_claim"] = complexity_claim

    # Merge demonstrated concepts (deduplicated)
    demonstrated = list(set(dsa_state.get("demonstrated_concepts", []) + new_concepts))
    dsa_state["demonstrated_concepts"] = demonstrated

    # Update missing concepts
    missing = [c for c in dsa_state.get("missing_concepts", []) if c not in demonstrated]
    dsa_state["missing_concepts"] = missing

    # Append new mistakes
    existing_mistakes = dsa_state.get("mistakes", [])
    for m in new_mistakes:
        m["turn_number"] = dsa_state.get("dsa_turn_count", 0)
        m["corrected"] = False
        m["correction_turn"] = None
        m["correction_how"] = "not_corrected"
        existing_mistakes.append(m)
    dsa_state["mistakes"] = existing_mistakes

    # Update scores (EXCLUDING code_correctness — set by executor only)
    current_scores = dsa_state.get("scores", {})
    evidence_no_code = [e for e in evidence_list if e.get("dimension") != "code_correctness"]
    updated_scores = _update_scores_from_evidence(current_scores, evidence_no_code)
    dsa_state["scores"] = updated_scores
    dsa_state["evidence_citations"] = existing_citations

    logger.info(
        f"[DSA/EVALUATOR] Extracted {len(evidence_list)} evidence items, "
        f"scores updated: {list(updated_scores.keys())}"
    )

    return {"dsa_state": dsa_state}
