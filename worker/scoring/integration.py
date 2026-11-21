"""Scoring Integration for the Interview Graph.

This module provides integration between the evidence-based skill tree
scoring system and the dual-brain interview graph.

It handles:
1. Initializing skill trees from job descriptions
2. Processing Q&A exchanges to extract evidence
3. Updating skill levels based on extracted evidence
4. Generating next question suggestions
5. Calculating final scores and Elo rankings
"""

import logging
from typing import Any

from redis.asyncio import Redis

from brain.state import InterviewState, SkillTreeState
from scoring.elo_system import EloSystem
from scoring.evidence_extractor import EvidenceExtractor
from scoring.jd_parser import JDParser
from scoring.ladder_generator import SkillLadderGenerator
from scoring.models import (
    CandidateSkillTree,
    QAExchange,
    RoleRequirements,
    SkillLadder,
    SkillRequirement,
)
from scoring.question_selector import QuestionSelector
from scoring.score_calculator import ScoreCalculator
from scoring.tree_manager import SkillTreeManager

logger = logging.getLogger(__name__)


class ScoringIntegration:
    """Integrates skill tree scoring into the interview workflow.

    This class provides methods that can be called from the interview graph
    to maintain and update skill tree state throughout an interview.
    """

    def __init__(self, redis: Redis):
        """Initialize scoring integration.

        Args:
            redis: Async Redis client for state persistence
        """
        self.redis = redis
        self.jd_parser = JDParser()
        self.ladder_generator = SkillLadderGenerator()
        self.evidence_extractor = EvidenceExtractor()
        self.tree_manager = SkillTreeManager(redis)
        self.question_selector = QuestionSelector()
        self.score_calculator = ScoreCalculator()
        self.elo_system = EloSystem(redis, self.score_calculator)

    # =========================================================================
    # Initialization
    # =========================================================================

    async def initialize_scoring(
        self,
        session_id: str,
        candidate_id: str,
        job_description: str,
        role_id: str | None = None,
    ) -> SkillTreeState:
        """Initialize scoring for a new interview session.

        This should be called at the start of an interview to:
        1. Parse the job description for skills
        2. Generate skill ladders
        3. Initialize the candidate's skill tree

        Args:
            session_id: Interview session ID
            candidate_id: Candidate identifier
            job_description: Job description text
            role_id: Optional role identifier (generated if not provided)

        Returns:
            Initialized SkillTreeState
        """
        logger.info(f"[SCORING] Initializing scoring for session {session_id}")

        # Parse job description
        requirements = await self.jd_parser.parse(job_description)
        role_id = role_id or f"role_{session_id}"

        # Generate skill ladders
        ladders = await self.ladder_generator.generate_all_ladders(requirements)

        # Save ladders to Redis
        await self.tree_manager.save_role_ladders(role_id, ladders)

        # Initialize skill tree
        skill_names = [s.skill_name for s in requirements.skills]
        tree = await self.tree_manager.get_or_create_tree(
            candidate_id=candidate_id,
            session_id=session_id,
            role_id=role_id,
            skills=skill_names,
        )

        # Build skill tree state
        skill_weights = {s.skill_name: s.weight for s in requirements.skills}

        state = SkillTreeState(
            role_id=role_id,
            role_title=requirements.title,
            skill_weights=skill_weights,
            ladders_generated=True,
            ladder_data={name: ladder.model_dump() for name, ladder in ladders.items()},
            tree_initialized=True,
            current_levels={name: 0 for name in skill_names},
            evidence_counts={name: 0 for name in skill_names},
            recent_skills=[],
            next_suggested_skill=None,
            next_suggested_level=None,
            next_suggested_question=None,
            weighted_score=None,
            score_percentage=None,
            elo_rating=None,
            elo_percentile=None,
        )

        # Generate first question suggestion
        await self._update_question_suggestion(state, tree, requirements, ladders, 1)

        logger.info(
            f"[SCORING] Initialized scoring for session {session_id} with {len(skill_names)} skills"
        )

        return state

    # =========================================================================
    # Evidence Processing
    # =========================================================================

    async def process_exchange(
        self,
        state: InterviewState,
        interviewer_question: str,
        candidate_response: str,
    ) -> dict[str, Any]:
        """Process a Q&A exchange and update skill tree.

        This should be called after each Q&A exchange to:
        1. Extract evidence from the response
        2. Update skill levels
        3. Generate next question suggestion

        Args:
            state: Current interview state
            interviewer_question: Question that was asked
            candidate_response: Candidate's response

        Returns:
            Updates to apply to state
        """
        skill_tree_state = state.get("skill_tree")
        if not skill_tree_state or not skill_tree_state.get("tree_initialized"):
            logger.warning("[SCORING] Skill tree not initialized, skipping exchange processing")
            return {}

        session_id = state.get("session_id", "unknown")
        turn_count = state.get("turn_count", 1)

        logger.info(f"[SCORING] Processing exchange for session {session_id}, turn {turn_count}")

        # Get skill tree and ladders
        tree = await self.tree_manager.get_tree(session_id)
        if not tree:
            logger.error(f"[SCORING] No skill tree found for session {session_id}")
            return {}

        role_id = skill_tree_state.get("role_id", "")
        ladders = await self.tree_manager.get_role_ladders(role_id)
        if not ladders:
            logger.error(f"[SCORING] No ladders found for role {role_id}")
            return {}

        # Create Q&A exchange
        exchange = QAExchange(
            turn_number=turn_count,
            interviewer_question=interviewer_question,
            candidate_response=candidate_response,
        )

        # Get current levels for efficient extraction
        current_levels = self.tree_manager.get_current_levels(tree)

        # Extract evidence (batch extraction)
        extractions = await self.evidence_extractor.extract_batch(
            exchange=exchange,
            ladders=ladders,
            current_levels=current_levels,
        )

        # Apply extractions to tree
        if extractions:
            tree = await self.tree_manager.apply_extractions(
                session_id=session_id,
                extractions=extractions,
                exchange=exchange,
            )

        # Update skill tree state
        updated_levels = self.tree_manager.get_current_levels(tree)
        evidence_counts = {name: node.get_total_evidence() for name, node in tree.skills.items()}

        # Track recent skills (for question selection)
        recent_skills = list(skill_tree_state.get("recent_skills", []))
        for extraction in extractions:
            if extraction.answer == "Yes" and extraction.skill_name not in recent_skills:
                recent_skills.insert(0, extraction.skill_name)
        recent_skills = recent_skills[:5]  # Keep last 5

        # Build requirements for question selection
        requirements = RoleRequirements(
            title=skill_tree_state.get("role_title", ""),
            skills=[
                SkillRequirement(skill_name=name, weight=weight)
                for name, weight in skill_tree_state.get("skill_weights", {}).items()
            ],
        )

        # Build updated state
        updated_skill_tree = dict(skill_tree_state)
        updated_skill_tree["current_levels"] = updated_levels
        updated_skill_tree["evidence_counts"] = evidence_counts
        updated_skill_tree["recent_skills"] = recent_skills

        # Generate next question suggestion
        await self._update_question_suggestion(
            updated_skill_tree, tree, requirements, ladders, turn_count + 1
        )

        logger.info(
            f"[SCORING] Processed exchange for session {session_id}: "
            f"{len(extractions)} extractions, "
            f"levels updated: {updated_levels}"
        )

        return {"skill_tree": updated_skill_tree}

    async def _update_question_suggestion(
        self,
        skill_tree_state: dict[str, Any],
        tree: CandidateSkillTree,
        requirements: RoleRequirements,
        ladders: dict[str, SkillLadder],
        turn_number: int,
    ) -> None:
        """Update the next question suggestion in skill tree state."""
        recent_skills = skill_tree_state.get("recent_skills", [])

        decision = await self.question_selector.select_next_question(
            tree=tree,
            requirements=requirements,
            ladders=ladders,
            role_title=requirements.title,
            recent_skills=recent_skills,
            turn_number=turn_number,
        )

        if decision:
            skill_tree_state["next_suggested_skill"] = decision.target_skill
            skill_tree_state["next_suggested_level"] = decision.target_level
            skill_tree_state["next_suggested_question"] = decision.suggested_question
        else:
            skill_tree_state["next_suggested_skill"] = None
            skill_tree_state["next_suggested_level"] = None
            skill_tree_state["next_suggested_question"] = None

    # =========================================================================
    # Score Calculation
    # =========================================================================

    async def calculate_final_score(
        self,
        state: InterviewState,
    ) -> dict[str, Any]:
        """Calculate final score at interview end.

        Args:
            state: Current interview state

        Returns:
            Updates to apply to state with final scores
        """
        skill_tree_state = state.get("skill_tree")
        if not skill_tree_state or not skill_tree_state.get("tree_initialized"):
            logger.warning("[SCORING] Skill tree not initialized, cannot calculate score")
            return {}

        session_id = state.get("session_id", "unknown")
        logger.info(f"[SCORING] Calculating final score for session {session_id}")

        # Get skill tree
        tree = await self.tree_manager.get_tree(session_id)
        if not tree:
            logger.error(f"[SCORING] No skill tree found for session {session_id}")
            return {}

        # Build requirements
        requirements = RoleRequirements(
            title=skill_tree_state.get("role_title", ""),
            skills=[
                SkillRequirement(skill_name=name, weight=weight)
                for name, weight in skill_tree_state.get("skill_weights", {}).items()
            ],
        )

        # Calculate weighted score
        score = self.score_calculator.calculate_score(tree, requirements)

        # Update skill tree state with scores
        updated_skill_tree = dict(skill_tree_state)
        updated_skill_tree["weighted_score"] = score.total_weighted_score
        updated_skill_tree["score_percentage"] = score.percentage

        # Check for Elo rating
        role_id = skill_tree_state.get("role_id", "")
        if await self.elo_system.can_show_rankings(role_id):
            rating = await self.elo_system.get_rating(tree.candidate_id, role_id)
            rankings = await self.elo_system.get_role_rankings(role_id)

            if rankings:
                all_ratings = [r.rating for r in rankings]
                from scoring.elo_system import calculate_percentile

                percentile = calculate_percentile(rating.rating, all_ratings)

                updated_skill_tree["elo_rating"] = rating.rating
                updated_skill_tree["elo_percentile"] = percentile

        logger.info(
            f"[SCORING] Final score for session {session_id}: "
            f"{score.percentage:.1f}% (weighted: {score.total_weighted_score:.3f})"
        )

        return {"skill_tree": updated_skill_tree}

    # =========================================================================
    # API Helpers
    # =========================================================================

    async def get_skill_tree_visualization(
        self,
        session_id: str,
    ) -> dict[str, Any] | None:
        """Get skill tree data for frontend visualization.

        Args:
            session_id: Interview session ID

        Returns:
            Visualization data or None if not found
        """
        from scoring.tree_manager import get_tree_visualization_data

        tree = await self.tree_manager.get_tree(session_id)
        if not tree:
            return None

        return get_tree_visualization_data(tree)

    async def get_score_breakdown(
        self,
        session_id: str,
        skill_tree_state: SkillTreeState,
    ) -> dict[str, Any] | None:
        """Get detailed score breakdown for frontend.

        Args:
            session_id: Interview session ID
            skill_tree_state: Current skill tree state

        Returns:
            Score breakdown or None if not found
        """
        tree = await self.tree_manager.get_tree(session_id)
        if not tree:
            return None

        requirements = RoleRequirements(
            title=skill_tree_state.get("role_title", ""),
            skills=[
                SkillRequirement(skill_name=name, weight=weight)
                for name, weight in skill_tree_state.get("skill_weights", {}).items()
            ],
        )

        score = self.score_calculator.calculate_score(tree, requirements)
        gaps = self.score_calculator.get_skill_gaps(score)
        strengths = self.score_calculator.get_strengths(score)

        return {
            "total_score": score.total_weighted_score,
            "percentage": score.percentage,
            "skill_scores": [s.model_dump() for s in score.skill_scores],
            "gaps": gaps,
            "strengths": strengths,
        }


# =============================================================================
# Graph Node Integration
# =============================================================================


async def scoring_process_exchange_node(state: InterviewState) -> dict[str, Any]:
    """LangGraph node for processing Q&A exchanges for scoring.

    This node should be called after the fast/slow brain generates a response.
    It extracts evidence from the exchange and updates the skill tree.

    Note: Requires Redis client to be available in the execution context.
    """
    from core.redis import redis_client

    skill_tree_state = state.get("skill_tree")
    if not skill_tree_state or not skill_tree_state.get("tree_initialized"):
        return {}

    # Get the most recent Q&A exchange
    messages = state.get("messages", [])
    if len(messages) < 2:
        return {}

    # Find the last assistant message (question) and user message (response)
    interviewer_question = None
    candidate_response = None

    for msg in reversed(messages):
        if msg["role"] == "user" and candidate_response is None:
            candidate_response = msg["content"]
        elif msg["role"] == "assistant" and interviewer_question is None:
            interviewer_question = msg["content"]
        if interviewer_question and candidate_response:
            break

    if not interviewer_question or not candidate_response:
        return {}

    async with redis_client() as redis:
        integration = ScoringIntegration(redis)
        return await integration.process_exchange(
            state=state,
            interviewer_question=interviewer_question,
            candidate_response=candidate_response,
        )


async def scoring_finalize_node(state: InterviewState) -> dict[str, Any]:
    """LangGraph node for calculating final scores at interview end.

    This node should be called when the interview concludes.
    """
    from core.redis import redis_client

    skill_tree_state = state.get("skill_tree")
    if not skill_tree_state or not skill_tree_state.get("tree_initialized"):
        return {}

    async with redis_client() as redis:
        integration = ScoringIntegration(redis)
        return await integration.calculate_final_score(state)


# =============================================================================
# Utility Functions
# =============================================================================


def get_suggested_question(state: InterviewState) -> str | None:
    """Get the suggested next question from skill tree state.

    This can be used by the fast brain to incorporate skill-targeted
    questions into the interview flow.

    Args:
        state: Current interview state

    Returns:
        Suggested question or None
    """
    skill_tree_state = state.get("skill_tree")
    if not skill_tree_state:
        return None

    return skill_tree_state.get("next_suggested_question")


def get_skill_summary(state: InterviewState) -> dict[str, Any] | None:
    """Get a summary of current skill assessment progress.

    Args:
        state: Current interview state

    Returns:
        Skill summary or None
    """
    skill_tree_state = state.get("skill_tree")
    if not skill_tree_state:
        return None

    current_levels = skill_tree_state.get("current_levels", {})
    skill_weights = skill_tree_state.get("skill_weights", {})

    skills = []
    for name, level in current_levels.items():
        weight = skill_weights.get(name, 0)
        skills.append(
            {
                "skill": name,
                "level": level,
                "weight": weight,
                "progress": level / 5.0,
            }
        )

    # Sort by weight
    skills.sort(key=lambda x: x["weight"], reverse=True)

    return {
        "skills": skills,
        "total_skills": len(skills),
        "assessed_skills": sum(1 for s in skills if s["level"] > 0),
        "average_level": sum(s["level"] for s in skills) / len(skills) if skills else 0,
    }
