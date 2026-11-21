"""Question Selector for nudging interviews toward unexplored skills.

This module provides intelligent question selection that:
1. Prioritizes high-weight skills that haven't been assessed
2. Targets the next level for partially assessed skills
3. Balances exploration vs. depth in skill assessment
4. Generates contextual questions based on skill ladders
"""

import logging
from typing import Any

from dotenv import load_dotenv

from core.llm_text import message_text
from scoring.models import CandidateSkillTree, NextQuestionDecision, RoleRequirements, SkillLadder

load_dotenv()


logger = logging.getLogger(__name__)

# Prompt for generating contextual questions
QUESTION_GENERATION_PROMPT = """You are an expert technical interviewer. Generate a natural interview question to assess the candidate's skills.

SKILL TO PROBE: {skill_name}
TARGET LEVEL: {target_level} ({level_description})
BINARY ASSESSMENT QUESTION: {binary_question}

EVIDENCE HINTS (what we're looking for):
{evidence_hints}

INTERVIEW CONTEXT:
- Role: {role_title}
- Skills already discussed: {skills_discussed}
- Current turn: {turn_number}

Generate a conversational interview question that will naturally elicit evidence for the binary assessment question. The question should:
1. Sound natural and conversational, not like a test
2. Give the candidate room to demonstrate their depth
3. Be specific enough to get useful evidence
4. Build on previous conversation if relevant

Respond with ONLY the question text, nothing else.
"""


class QuestionSelector:
    """Selects the next interview question based on skill tree state.

    Uses a priority algorithm that balances:
    - Skill weight (importance to the role)
    - Remaining potential (unexplored levels)
    - Recency (avoid asking about the same skill repeatedly)
    """

    def __init__(self, llm: Any | None = None):
        """Initialize the question selector.

        Args:
            llm: LangChain-compatible LLM for question generation (optional)
        """
        self._llm = llm

    @property
    def llm(self) -> Any:
        """Lazy-load LLM instance."""
        if self._llm is None:
            from scoring.llm_client import scoring_llm

            self._llm = scoring_llm(temperature=0.3)
        return self._llm

    def calculate_skill_priorities(
        self,
        tree: CandidateSkillTree,
        requirements: RoleRequirements,
        recent_skills: list[str] | None = None,
        recency_penalty: float = 0.3,
    ) -> list[tuple[str, float, int, float]]:
        """Calculate priority scores for each skill.

        Priority = weight * remaining_potential * recency_factor

        Args:
            tree: Current skill tree state
            requirements: Role requirements with skill weights
            recent_skills: Skills discussed in recent turns (penalized)
            recency_penalty: Penalty multiplier for recent skills

        Returns:
            List of (skill_name, weight, current_level, priority) tuples,
            sorted by priority descending
        """
        if recent_skills is None:
            recent_skills = []

        skill_weights = {s.skill_name: s.weight for s in requirements.skills}
        priorities = []

        for skill_name, weight in skill_weights.items():
            node = tree.skills.get(skill_name)
            current_level = node.current_level if node else 0

            # Remaining potential (levels left to explore)
            remaining = 5 - current_level
            if remaining <= 0:
                continue  # Skip maxed-out skills

            # Recency factor (penalize recently discussed skills)
            recency_factor = 1.0
            if skill_name in recent_skills:
                position = recent_skills.index(skill_name)
                # More recent = higher penalty
                recency_factor = recency_penalty ** (len(recent_skills) - position)

            # Calculate priority
            priority = weight * remaining * recency_factor

            priorities.append((skill_name, weight, current_level, priority))

        # Sort by priority (descending)
        priorities.sort(key=lambda x: x[3], reverse=True)

        return priorities

    def select_target_skill(
        self,
        tree: CandidateSkillTree,
        requirements: RoleRequirements,
        recent_skills: list[str] | None = None,
    ) -> tuple[str, int] | None:
        """Select the best skill and level to probe next.

        Args:
            tree: Current skill tree state
            requirements: Role requirements
            recent_skills: Recently discussed skills

        Returns:
            (skill_name, target_level) or None if all skills maxed
        """
        priorities = self.calculate_skill_priorities(tree, requirements, recent_skills)

        if not priorities:
            logger.info("All skills at maximum level")
            return None

        # Select highest priority skill
        skill_name, weight, current_level, priority = priorities[0]
        target_level = current_level + 1

        logger.debug(
            f"Selected skill '{skill_name}' (weight={weight:.2f}, "
            f"current={current_level}, target={target_level}, priority={priority:.3f})"
        )

        return (skill_name, target_level)

    async def generate_question(
        self,
        skill_name: str,
        target_level: int,
        ladder: SkillLadder,
        role_title: str,
        skills_discussed: list[str],
        turn_number: int,
    ) -> str:
        """Generate a natural interview question for the target skill/level.

        Args:
            skill_name: Skill to probe
            target_level: Level to target
            ladder: Skill ladder with binary questions
            role_title: Role being interviewed for
            skills_discussed: Skills already discussed
            turn_number: Current turn number

        Returns:
            Generated interview question
        """
        level = ladder.get_level(target_level)
        if not level:
            # Fallback to generic question
            return f"Can you tell me about your experience with {skill_name}?"

        level_descriptions = {
            1: "Awareness - has the candidate heard of this",
            2: "Conceptual - can they explain what it is",
            3: "Practical - have they used it in real projects",
            4: "Problem-Solving - have they solved challenges with it",
            5: "Mastery - have they optimized or architected with it",
        }

        prompt = QUESTION_GENERATION_PROMPT.format(
            skill_name=skill_name,
            target_level=target_level,
            level_description=level_descriptions.get(target_level, ""),
            binary_question=level.binary_question,
            evidence_hints="\n".join(f"- {hint}" for hint in level.evidence_hints),
            role_title=role_title,
            skills_discussed=(
                ", ".join(skills_discussed) if skills_discussed else "None yet"
            ),
            turn_number=turn_number,
        )

        try:
            response = await self.llm.ainvoke(prompt)
            return message_text(response).strip()
        except Exception as e:
            logger.error(f"Failed to generate question: {e}")
            # Fallback to the binary question itself
            return f"Regarding {skill_name}: {level.binary_question}"

    async def select_next_question(
        self,
        tree: CandidateSkillTree,
        requirements: RoleRequirements,
        ladders: dict[str, SkillLadder],
        role_title: str,
        recent_skills: list[str] | None = None,
        turn_number: int = 1,
    ) -> NextQuestionDecision | None:
        """Select and generate the next interview question.

        Args:
            tree: Current skill tree state
            requirements: Role requirements
            ladders: Skill ladders for question hints
            role_title: Role title for context
            recent_skills: Recently discussed skills
            turn_number: Current turn number

        Returns:
            NextQuestionDecision or None if interview should end
        """
        # Select target skill
        selection = self.select_target_skill(tree, requirements, recent_skills)
        if not selection:
            return None

        skill_name, target_level = selection

        # Get ladder for this skill
        ladder = ladders.get(skill_name)
        if not ladder:
            logger.warning(f"No ladder found for skill '{skill_name}'")
            # Create a basic question
            return NextQuestionDecision(
                target_skill=skill_name,
                target_level=target_level,
                suggested_question=f"Tell me about your experience with {skill_name}.",
                reasoning="No ladder available, using generic question",
                exploration_value=self._calculate_exploration_value(
                    tree, requirements, skill_name, target_level
                ),
            )

        # Generate contextual question
        skills_discussed = tree.get_assessed_skills()
        question = await self.generate_question(
            skill_name=skill_name,
            target_level=target_level,
            ladder=ladder,
            role_title=role_title,
            skills_discussed=skills_discussed,
            turn_number=turn_number,
        )

        # Calculate exploration value
        exploration_value = self._calculate_exploration_value(
            tree, requirements, skill_name, target_level
        )

        # Build reasoning
        skill_weight = next(
            (s.weight for s in requirements.skills if s.skill_name == skill_name), 0.0
        )
        current_level = tree.skills.get(skill_name)
        current = current_level.current_level if current_level else 0

        reasoning = (
            f"Targeting {skill_name} (weight={skill_weight:.0%}) at level {target_level}. "
            f"Currently at level {current}. "
            f"Exploration value: {exploration_value:.2f}"
        )

        return NextQuestionDecision(
            target_skill=skill_name,
            target_level=target_level,
            suggested_question=question,
            reasoning=reasoning,
            exploration_value=exploration_value,
        )

    def _calculate_exploration_value(
        self,
        tree: CandidateSkillTree,
        requirements: RoleRequirements,
        skill_name: str,
        target_level: int,
    ) -> float:
        """Calculate the exploration value of probing a skill.

        Higher values indicate more valuable exploration:
        - High-weight skills are more valuable
        - Lower current levels have more upside
        - Earlier target levels are easier to confirm

        Args:
            tree: Current skill tree
            requirements: Role requirements
            skill_name: Skill to evaluate
            target_level: Level being targeted

        Returns:
            Exploration value score (0.0 - 1.0)
        """
        # Get skill weight
        weight = next(
            (s.weight for s in requirements.skills if s.skill_name == skill_name), 0.0
        )

        # Get current level
        node = tree.skills.get(skill_name)
        current_level = node.current_level if node else 0

        # Remaining potential (normalized)
        remaining = (5 - current_level) / 5.0

        # Target difficulty (lower targets are easier to achieve)
        difficulty_factor = 1.0 - (target_level - 1) / 4.0

        # Combine factors
        exploration_value = weight * remaining * 0.5 + weight * difficulty_factor * 0.5

        return min(1.0, exploration_value)

    def get_skills_summary(
        self,
        tree: CandidateSkillTree,
        requirements: RoleRequirements,
    ) -> dict[str, Any]:
        """Get a summary of skill assessment progress.

        Args:
            tree: Current skill tree
            requirements: Role requirements

        Returns:
            Dict with assessment summary
        """
        skill_weights = {s.skill_name: s.weight for s in requirements.skills}
        total_skills = len(skill_weights)

        assessed = 0
        fully_assessed = 0
        total_weighted_progress = 0.0

        skills_detail = []

        for skill_name, weight in skill_weights.items():
            node = tree.skills.get(skill_name)
            current = node.current_level if node else 0
            evidence_count = node.get_total_evidence() if node else 0

            if current > 0:
                assessed += 1
            if current >= 5:
                fully_assessed += 1

            progress = current / 5.0
            total_weighted_progress += progress * weight

            skills_detail.append(
                {
                    "skill": skill_name,
                    "weight": weight,
                    "current_level": current,
                    "progress": progress,
                    "evidence_count": evidence_count,
                }
            )

        return {
            "total_skills": total_skills,
            "skills_assessed": assessed,
            "skills_fully_assessed": fully_assessed,
            "weighted_progress": total_weighted_progress,
            "skills": sorted(skills_detail, key=lambda x: x["weight"], reverse=True),
        }


# =============================================================================
# Utility Functions
# =============================================================================


def get_default_question_for_skill(skill_name: str, level: int) -> str:
    """Get a default question for a skill/level when LLM is unavailable.

    Args:
        skill_name: Skill name
        level: Target level (1-5)

    Returns:
        Default question string
    """
    templates = {
        1: f"Have you worked with {skill_name} before?",
        2: f"Can you explain what {skill_name} is and how it works?",
        3: f"Tell me about a project where you used {skill_name}.",
        4: f"What challenges have you faced when working with {skill_name}?",
        5: f"How would you architect a system using {skill_name} for scale?",
    }
    return templates.get(level, f"Tell me about your experience with {skill_name}.")


def should_continue_interview(
    tree: CandidateSkillTree,
    requirements: RoleRequirements,
    min_coverage: float = 0.6,
    max_turns: int = 15,
    current_turn: int = 1,
) -> bool:
    """Determine if the interview should continue.

    Args:
        tree: Current skill tree
        requirements: Role requirements
        min_coverage: Minimum weighted progress before stopping
        max_turns: Maximum interview turns
        current_turn: Current turn number

    Returns:
        True if interview should continue
    """
    # Hard stop at max turns
    if current_turn >= max_turns:
        logger.info(f"Reached max turns ({max_turns})")
        return False

    # Calculate current coverage
    skill_weights = {s.skill_name: s.weight for s in requirements.skills}
    total_weighted_progress = 0.0

    for skill_name, weight in skill_weights.items():
        node = tree.skills.get(skill_name)
        current = node.current_level if node else 0
        total_weighted_progress += (current / 5.0) * weight

    # Check if we've met minimum coverage
    if total_weighted_progress >= min_coverage:
        logger.info(
            f"Met minimum coverage ({total_weighted_progress:.0%} >= {min_coverage:.0%})"
        )
        return False

    return True
