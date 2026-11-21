"""Weighted Score Calculator for candidate evaluation.

This module calculates weighted scores from skill trees by:
1. Applying skill weights from role requirements
2. Accounting for skill transferability
3. Providing detailed score breakdowns
"""

import logging
from typing import Any

from scoring.models import (
    CandidateSkillTree,
    RoleRequirements,
    SkillScore,
    SkillTransferability,
    WeightedScore,
)

logger = logging.getLogger(__name__)


class ScoreCalculator:
    """Calculates weighted scores from candidate skill trees.

    Produces transparent, evidence-backed scores with full breakdown
    of how each skill contributed to the final score.
    """

    def __init__(
        self,
        transferability_graph: list[SkillTransferability] | None = None,
    ):
        """Initialize the score calculator.

        Args:
            transferability_graph: Optional skill transfer relationships
        """
        self.transferability_graph = transferability_graph or []
        self._transfer_map = self._build_transfer_map()

    def _build_transfer_map(self) -> dict[str, list[tuple[str, float]]]:
        """Build a lookup map for skill transfers.

        Returns:
            Dict mapping target skill to list of (source_skill, weight) tuples
        """
        transfer_map: dict[str, list[tuple[str, float]]] = {}

        for transfer in self.transferability_graph:
            if transfer.to_skill not in transfer_map:
                transfer_map[transfer.to_skill] = []
            transfer_map[transfer.to_skill].append((transfer.from_skill, transfer.transfer_weight))

        return transfer_map

    def calculate_score(
        self,
        tree: CandidateSkillTree,
        requirements: RoleRequirements,
    ) -> WeightedScore:
        """Calculate weighted score for a candidate.

        Args:
            tree: Candidate's skill tree
            requirements: Role requirements with skill weights

        Returns:
            WeightedScore with detailed breakdown
        """
        skill_scores: list[SkillScore] = []
        total_weighted_score = 0.0

        for skill_req in requirements.skills:
            skill_name = skill_req.skill_name
            weight = skill_req.weight

            # Get base level from skill tree
            node = tree.skills.get(skill_name)
            base_level = node.current_level if node else 0
            evidence_count = node.get_total_evidence() if node else 0

            # Check for skill transfer contributions
            transfer_contribution = 0.0
            transferred_from = None

            if base_level < 5 and skill_name in self._transfer_map:
                # Look for transferable skills
                for source_skill, transfer_weight in self._transfer_map[skill_name]:
                    source_node = tree.skills.get(source_skill)
                    if source_node and source_node.current_level > 0:
                        # Calculate transfer contribution
                        # Transfer can boost up to the source skill's level * transfer_weight
                        potential_boost = source_node.current_level * transfer_weight
                        if potential_boost > transfer_contribution:
                            transfer_contribution = potential_boost
                            transferred_from = source_skill

            # Calculate effective level (capped at 5)
            effective_level = min(5, base_level + transfer_contribution)
            weighted_contribution = (effective_level / 5.0) * weight

            skill_scores.append(
                SkillScore(
                    skill_name=skill_name,
                    achieved_level=base_level,
                    max_level=5,
                    weight=weight,
                    weighted_contribution=weighted_contribution,
                    evidence_count=evidence_count,
                    transferred_from=transferred_from,
                    transfer_contribution=transfer_contribution,
                )
            )

            total_weighted_score += weighted_contribution

        # Calculate percentage (max possible is 1.0 when all skills at level 5)
        percentage = total_weighted_score * 100

        return WeightedScore(
            candidate_id=tree.candidate_id,
            session_id=tree.session_id,
            role_id=tree.role_id,
            skill_scores=skill_scores,
            total_weighted_score=total_weighted_score,
            max_possible_score=1.0,
            percentage=percentage,
        )

    def get_skill_gaps(
        self,
        score: WeightedScore,
        min_gap_weight: float = 0.1,
    ) -> list[dict[str, Any]]:
        """Identify skill gaps based on score.

        Args:
            score: Calculated weighted score
            min_gap_weight: Minimum skill weight to consider a gap

        Returns:
            List of gap details sorted by impact
        """
        gaps = []

        for skill_score in score.skill_scores:
            if skill_score.weight < min_gap_weight:
                continue

            gap = skill_score.max_level - skill_score.achieved_level
            if gap > 0:
                # Calculate impact: weight * gap
                impact = skill_score.weight * (gap / skill_score.max_level)

                gaps.append(
                    {
                        "skill": skill_score.skill_name,
                        "current_level": skill_score.achieved_level,
                        "max_level": skill_score.max_level,
                        "gap": gap,
                        "weight": skill_score.weight,
                        "impact": impact,
                        "evidence_count": skill_score.evidence_count,
                    }
                )

        # Sort by impact (descending)
        gaps.sort(key=lambda x: x["impact"], reverse=True)

        return gaps

    def get_strengths(
        self,
        score: WeightedScore,
        min_level: int = 3,
    ) -> list[dict[str, Any]]:
        """Identify candidate strengths based on score.

        Args:
            score: Calculated weighted score
            min_level: Minimum level to consider a strength

        Returns:
            List of strength details sorted by contribution
        """
        strengths = []

        for skill_score in score.skill_scores:
            if skill_score.achieved_level >= min_level:
                strengths.append(
                    {
                        "skill": skill_score.skill_name,
                        "level": skill_score.achieved_level,
                        "weight": skill_score.weight,
                        "contribution": skill_score.weighted_contribution,
                        "evidence_count": skill_score.evidence_count,
                        "transferred_from": skill_score.transferred_from,
                    }
                )

        # Sort by contribution (descending)
        strengths.sort(key=lambda x: x["contribution"], reverse=True)

        return strengths


# =============================================================================
# Utility Functions
# =============================================================================


def format_score_for_display(score: WeightedScore) -> str:
    """Format a weighted score for text display.

    Args:
        score: WeightedScore to format

    Returns:
        Formatted string
    """
    lines = [
        f"Candidate Score: {score.percentage:.1f}%",
        f"Total Weighted: {score.total_weighted_score:.3f} / {score.max_possible_score:.3f}",
        "",
        "Skill Breakdown:",
    ]

    for skill in sorted(score.skill_scores, key=lambda s: s.weight, reverse=True):
        level_bar = "█" * skill.achieved_level + "░" * (5 - skill.achieved_level)
        transfer_note = (
            f" (+{skill.transfer_contribution:.1f} from {skill.transferred_from})"
            if skill.transferred_from
            else ""
        )
        lines.append(
            f"  {skill.skill_name}: [{level_bar}] L{skill.achieved_level}/5 "
            f"(w={skill.weight:.0%}){transfer_note}"
        )

    return "\n".join(lines)


def compare_scores(score_a: WeightedScore, score_b: WeightedScore) -> dict[str, Any]:
    """Compare two candidate scores.

    Args:
        score_a: First candidate's score
        score_b: Second candidate's score

    Returns:
        Comparison details
    """
    # Build skill maps
    skills_a = {s.skill_name: s for s in score_a.skill_scores}
    skills_b = {s.skill_name: s for s in score_b.skill_scores}

    all_skills = set(skills_a.keys()) | set(skills_b.keys())

    skill_comparisons = []
    for skill_name in all_skills:
        s_a = skills_a.get(skill_name)
        s_b = skills_b.get(skill_name)

        level_a = s_a.achieved_level if s_a else 0
        level_b = s_b.achieved_level if s_b else 0
        weight = (s_a.weight if s_a else 0) or (s_b.weight if s_b else 0)

        if level_a > level_b:
            winner = "a"
        elif level_b > level_a:
            winner = "b"
        else:
            winner = "tie"

        skill_comparisons.append(
            {
                "skill": skill_name,
                "level_a": level_a,
                "level_b": level_b,
                "weight": weight,
                "winner": winner,
            }
        )

    # Overall winner
    if score_a.total_weighted_score > score_b.total_weighted_score:
        overall_winner = "a"
    elif score_b.total_weighted_score > score_a.total_weighted_score:
        overall_winner = "b"
    else:
        overall_winner = "tie"

    return {
        "candidate_a": score_a.candidate_id,
        "candidate_b": score_b.candidate_id,
        "score_a": score_a.total_weighted_score,
        "score_b": score_b.total_weighted_score,
        "percentage_a": score_a.percentage,
        "percentage_b": score_b.percentage,
        "skill_comparisons": skill_comparisons,
        "overall_winner": overall_winner,
    }
