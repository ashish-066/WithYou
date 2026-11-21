"""Job Description Parser for extracting skill requirements.

This module uses LLM to parse job descriptions and extract structured
skill requirements with weights.
"""

import json
import logging
from typing import Any

from dotenv import load_dotenv
from pydantic import ValidationError

from core.llm_text import message_text
from scoring.models import RoleRequirements, SkillRequirement

load_dotenv()

logger = logging.getLogger(__name__)

# Prompt for extracting skills from JD
JD_PARSER_PROMPT = """You are an expert technical recruiter. Analyze the following job description and extract the key technical skills required.

JOB DESCRIPTION:
{jd_text}

Extract 4-6 key technical skills that are MOST important for this role. For each skill:
1. Identify the skill name (be specific, e.g., "Distributed Caching" not just "Caching")
2. Assign a weight (0.0-1.0) based on importance. Weights MUST sum to 1.0.
3. List related skills that could transfer (e.g., for AWS, list GCP, Azure)
4. Provide context from the JD about why this skill matters

RESPOND IN EXACTLY THIS JSON FORMAT:
{{
    "title": "Job title from the JD",
    "skills": [
        {{
            "skill_name": "Skill Name",
            "weight": 0.25,
            "related_skills": ["Related Skill 1", "Related Skill 2"],
            "context": "Why this skill matters for the role"
        }}
    ]
}}

IMPORTANT:
- Extract 4-6 skills maximum
- Weights MUST sum to exactly 1.0
- Be specific with skill names (not generic terms)
- Include only technical skills, not soft skills
- Related skills should be genuinely transferable (e.g., different cloud providers, similar frameworks)
"""


class JDParser:
    """Parses job descriptions to extract structured skill requirements.

    Uses LLM to analyze JD text and extract skills with weights and
    transferability relationships.
    """

    def __init__(self, llm: Any | None = None):
        """Initialize the JD Parser.

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

            self._llm = scoring_llm(temperature=0.1)
        return self._llm

    async def parse(self, jd_text: str) -> RoleRequirements:
        """Parse a job description and extract skill requirements.

        Args:
            jd_text: Raw job description text

        Returns:
            RoleRequirements with extracted skills and weights

        Raises:
            ValueError: If parsing fails or validation errors occur
        """
        logger.info("Parsing job description for skill requirements")

        prompt = JD_PARSER_PROMPT.format(jd_text=jd_text)

        try:
            response = await self.llm.ainvoke(prompt)
            content = message_text(response)

            # Parse JSON from response
            parsed = self._extract_json(content)

            # Validate and normalize weights
            parsed = self._normalize_weights(parsed)

            # Create and validate model
            requirements = RoleRequirements(
                title=parsed.get("title", "Unknown Role"),
                skills=[SkillRequirement(**skill) for skill in parsed.get("skills", [])],
            )

            # Validate weights sum
            if not requirements.validate_weights():
                logger.warning("Weights don't sum to 1.0, normalizing...")
                requirements = self._force_normalize_weights(requirements)

            logger.info(
                f"Extracted {len(requirements.skills)} skills for role: {requirements.title}"
            )
            return requirements

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON from LLM response: {e}")
            raise ValueError(f"Failed to parse JD: Invalid JSON response - {e}")
        except ValidationError as e:
            logger.error(f"Validation error: {e}")
            raise ValueError(f"Failed to parse JD: Validation error - {e}")
        except Exception as e:
            logger.error(f"Error parsing JD: {e}")
            raise ValueError(f"Failed to parse JD: {e}")

    def _extract_json(self, content: str) -> dict[str, Any]:
        """Extract JSON from LLM response content.

        Handles cases where JSON is wrapped in markdown code blocks.
        """
        # Try to find JSON in markdown code blocks
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

    def _normalize_weights(self, parsed: dict[str, Any]) -> dict[str, Any]:
        """Normalize weights to sum to 1.0."""
        skills = parsed.get("skills", [])
        if not skills:
            return parsed

        total_weight = sum(s.get("weight", 0) for s in skills)
        if total_weight > 0 and abs(total_weight - 1.0) > 0.01:
            for skill in skills:
                skill["weight"] = skill.get("weight", 0) / total_weight

        return parsed

    def _force_normalize_weights(self, requirements: RoleRequirements) -> RoleRequirements:
        """Force normalize weights in a RoleRequirements object."""
        total = sum(s.weight for s in requirements.skills)
        if total > 0:
            for skill in requirements.skills:
                skill.weight = skill.weight / total
        return requirements

    async def parse_with_retry(self, jd_text: str, max_retries: int = 2) -> RoleRequirements:
        """Parse JD with retries on failure.

        Args:
            jd_text: Raw job description text
            max_retries: Maximum retry attempts

        Returns:
            RoleRequirements with extracted skills
        """
        last_error: Exception | None = None

        for attempt in range(max_retries + 1):
            try:
                return await self.parse(jd_text)
            except ValueError as e:
                last_error = e
                logger.warning(f"Parse attempt {attempt + 1} failed: {e}")
                if attempt < max_retries:
                    continue

        raise last_error or ValueError("Failed to parse JD after retries")


# =============================================================================
# Utility Functions
# =============================================================================


def create_default_requirements(title: str = "Software Engineer") -> RoleRequirements:
    """Create default role requirements for testing.

    Args:
        title: Role title

    Returns:
        RoleRequirements with generic software engineering skills
    """
    return RoleRequirements(
        title=title,
        skills=[
            SkillRequirement(
                skill_name="Problem Solving",
                weight=0.25,
                related_skills=[],
                context="Core engineering skill",
            ),
            SkillRequirement(
                skill_name="System Design",
                weight=0.25,
                related_skills=[],
                context="Ability to design scalable systems",
            ),
            SkillRequirement(
                skill_name="Coding Proficiency",
                weight=0.25,
                related_skills=[],
                context="Writing clean, maintainable code",
            ),
            SkillRequirement(
                skill_name="Technical Communication",
                weight=0.25,
                related_skills=[],
                context="Explaining technical concepts clearly",
            ),
        ],
    )
