"""Skill Ladder Generator for creating depth assessment questions.

This module generates 5-level depth ladders for each skill, where each level
is a binary question that determines if the candidate has achieved that depth.
"""

import asyncio
import json
import logging
from typing import Any

from dotenv import load_dotenv

load_dotenv()

from pydantic import ValidationError

from core.llm_text import message_text
from scoring.models import LadderLevel, RoleRequirements, SkillLadder, SkillRequirement

logger = logging.getLogger(__name__)

# Prompt for generating skill ladders
LADDER_GENERATION_PROMPT = """You are an expert technical interviewer. Generate a 5-level depth ladder for assessing the skill "{skill_name}" in the context of a {role_title} role.

SKILL CONTEXT:
{skill_context}

Each level should be a BINARY (Yes/No) question that can be answered from interview transcript.
The levels represent increasing depth:
- Level 1 (Awareness): Has the candidate mentioned or referenced this concept?
- Level 2 (Conceptual): Can they explain what it is and basic principles?
- Level 3 (Practical): Have they described real hands-on experience?
- Level 4 (Problem-Solving): Have they discussed challenges, edge cases, or debugging?
- Level 5 (Mastery): Have they demonstrated optimization, architecture decisions, or teaching ability?

For each level, provide:
1. A clear binary question
2. 2-3 evidence hints (phrases/concepts that would indicate "Yes")
3. An example "Yes" answer snippet
4. An example "No" answer snippet (what insufficient would look like)

RESPOND IN EXACTLY THIS JSON FORMAT:
{{
    "skill_name": "{skill_name}",
    "levels": [
        {{
            "level": 1,
            "binary_question": "Did the candidate mention or reference [specific concept]?",
            "evidence_hints": ["hint 1", "hint 2", "hint 3"],
            "example_yes": "Example of what a Yes answer looks like",
            "example_no": "Example of what an insufficient answer looks like"
        }},
        {{
            "level": 2,
            "binary_question": "...",
            "evidence_hints": ["...", "...", "..."],
            "example_yes": "...",
            "example_no": "..."
        }},
        {{
            "level": 3,
            "binary_question": "...",
            "evidence_hints": ["...", "...", "..."],
            "example_yes": "...",
            "example_no": "..."
        }},
        {{
            "level": 4,
            "binary_question": "...",
            "evidence_hints": ["...", "...", "..."],
            "example_yes": "...",
            "example_no": "..."
        }},
        {{
            "level": 5,
            "binary_question": "...",
            "evidence_hints": ["...", "...", "..."],
            "example_yes": "...",
            "example_no": "..."
        }}
    ]
}}

IMPORTANT:
- Questions must be answerable with Yes/No from transcript alone
- Each level should be strictly harder than the previous
- Evidence hints should be specific technical terms/concepts
- Examples should be realistic interview snippets
- Higher levels should implicitly require lower levels
"""


class SkillLadderGenerator:
    """Generates depth ladders for skills extracted from job descriptions.

    Creates a 5-level binary question ladder for each skill that can be
    used to objectively assess candidate depth during interviews.
    """

    def __init__(self, llm: Any | None = None):
        """Initialize the ladder generator.

        Args:
            llm: LangChain-compatible LLM instance. If None, will be initialized
                 when needed.
        """
        self._llm = llm

    @property
    def llm(self) -> Any:
        """Lazy-load LLM instance."""
        if self._llm is None:
            from scoring.llm_client import scoring_llm

            self._llm = scoring_llm(temperature=0.2)
        return self._llm

    async def generate_ladder(self, skill: SkillRequirement, role_title: str) -> SkillLadder:
        """Generate a depth ladder for a single skill.

        Args:
            skill: The skill requirement to generate a ladder for
            role_title: The role title for context

        Returns:
            SkillLadder with 5 levels of binary questions
        """
        logger.info(f"Generating ladder for skill: {skill.skill_name}")

        prompt = LADDER_GENERATION_PROMPT.format(
            skill_name=skill.skill_name,
            role_title=role_title,
            skill_context=skill.context or f"Required skill for {role_title}",
        )

        try:
            response = await self.llm.ainvoke(prompt)
            content = message_text(response)

            # Parse JSON
            parsed = self._extract_json(content)

            # Create ladder
            ladder = SkillLadder(
                skill_name=skill.skill_name,
                levels=[LadderLevel(**level) for level in parsed.get("levels", [])],
            )

            # Validate we have 5 levels
            if len(ladder.levels) != 5:
                logger.warning(f"Expected 5 levels, got {len(ladder.levels)}. Padding/trimming...")
                ladder = self._ensure_five_levels(ladder, skill.skill_name)

            logger.info(f"Generated ladder for {skill.skill_name} with 5 levels")
            return ladder

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON for {skill.skill_name}: {e}")
            return self._create_fallback_ladder(skill.skill_name)
        except ValidationError as e:
            logger.error(f"Validation error for {skill.skill_name}: {e}")
            return self._create_fallback_ladder(skill.skill_name)
        except Exception as e:
            logger.error(f"Error generating ladder for {skill.skill_name}: {e}")
            return self._create_fallback_ladder(skill.skill_name)

    async def generate_all_ladders(self, requirements: RoleRequirements) -> dict[str, SkillLadder]:
        """Generate ladders for all skills in the role requirements.

        Args:
            requirements: RoleRequirements with skills

        Returns:
            Dict mapping skill name to SkillLadder
        """
        logger.info(
            f"Generating ladders for {len(requirements.skills)} skills "
            f"for role: {requirements.title}"
        )

        # Generate all ladders in parallel for better performance
        tasks = [self.generate_ladder(skill, requirements.title) for skill in requirements.skills]
        results = await asyncio.gather(*tasks)

        ladders = {skill.skill_name: ladder for skill, ladder in zip(requirements.skills, results)}

        logger.info(f"Generated {len(ladders)} skill ladders")
        return ladders

    def _extract_json(self, content: str) -> dict[str, Any]:
        """Extract JSON from LLM response."""
        if "```json" in content:
            start = content.find("```json") + 7
            end = content.find("```", start)
            if end == -1:
                content = content[start:].strip()
            else:
                content = content[start:end].strip()
        elif "```" in content:
            start = content.find("```") + 3
            end = content.find("```", start)
            if end == -1:
                content = content[start:].strip()
            else:
                content = content[start:end].strip()

        return json.loads(content)

    def _ensure_five_levels(self, ladder: SkillLadder, skill_name: str) -> SkillLadder:
        """Ensure the ladder has exactly 5 levels."""
        existing_levels = {level.level: level for level in ladder.levels}

        complete_levels = []
        for i in range(1, 6):
            if i in existing_levels:
                complete_levels.append(existing_levels[i])
            else:
                # Create a placeholder level
                complete_levels.append(
                    LadderLevel(
                        level=i,
                        binary_question=f"Did the candidate demonstrate level {i} competency in {skill_name}?",
                        evidence_hints=[f"Level {i} evidence"],
                        example_yes=f"Example of level {i} competency",
                        example_no=f"Insufficient for level {i}",
                    )
                )

        return SkillLadder(
            skill_name=skill_name,
            levels=complete_levels,
            generated_at=ladder.generated_at,
        )

    def _create_fallback_ladder(self, skill_name: str) -> SkillLadder:
        """Create a generic fallback ladder when generation fails."""
        logger.warning(f"Creating fallback ladder for {skill_name}")

        level_descriptions = [
            ("Awareness", "mentioned or referenced"),
            ("Conceptual", "explained the concept or principles of"),
            ("Practical", "described hands-on experience with"),
            ("Problem-Solving", "discussed challenges or edge cases in"),
            ("Mastery", "demonstrated optimization or architecture decisions for"),
        ]

        levels = []
        for i, (level_name, verb) in enumerate(level_descriptions, 1):
            levels.append(
                LadderLevel(
                    level=i,
                    binary_question=f"Did the candidate {verb} {skill_name}?",
                    evidence_hints=[
                        f"{skill_name} {level_name.lower()}",
                        f"Level {i} indicator",
                    ],
                    example_yes=f"Candidate demonstrated {level_name.lower()} of {skill_name}",
                    example_no=f"Candidate did not reach {level_name.lower()} level",
                )
            )

        return SkillLadder(skill_name=skill_name, levels=levels)


# =============================================================================
# Utility Functions
# =============================================================================


def create_test_ladder(skill_name: str) -> SkillLadder:
    """Create a test ladder for development/testing.

    Args:
        skill_name: Name of the skill

    Returns:
        A complete SkillLadder with 5 levels
    """
    return SkillLadder(
        skill_name=skill_name,
        levels=[
            LadderLevel(
                level=1,
                binary_question=f"Did the candidate mention {skill_name}?",
                evidence_hints=["mentioned", "referenced", "talked about"],
                example_yes=f"I have some experience with {skill_name}",
                example_no="I haven't worked with that",
            ),
            LadderLevel(
                level=2,
                binary_question=f"Did the candidate explain what {skill_name} is?",
                evidence_hints=["is a", "means", "works by", "concept of"],
                example_yes=f"{skill_name} is a technique for...",
                example_no="I've heard of it but don't know much",
            ),
            LadderLevel(
                level=3,
                binary_question=f"Did the candidate describe using {skill_name} in a real project?",
                evidence_hints=["I used", "we implemented", "I built", "in production"],
                example_yes=f"I implemented {skill_name} in our payment system...",
                example_no="I've read about it but haven't used it",
            ),
            LadderLevel(
                level=4,
                binary_question=f"Did the candidate discuss challenges or debugging with {skill_name}?",
                evidence_hints=["problem was", "we fixed", "edge case", "challenge"],
                example_yes=f"We hit an issue with {skill_name} when...",
                example_no="It worked pretty smoothly, no issues",
            ),
            LadderLevel(
                level=5,
                binary_question=f"Did the candidate demonstrate mastery or architectural thinking about {skill_name}?",
                evidence_hints=[
                    "optimized",
                    "designed",
                    "architected",
                    "taught",
                    "led",
                ],
                example_yes=f"I redesigned our {skill_name} architecture to handle 10x scale...",
                example_no="I follow the patterns the team uses",
            ),
        ],
    )
