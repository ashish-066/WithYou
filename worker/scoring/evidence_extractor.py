"""Evidence Extractor using constrained LLM calls.

This module extracts evidence from interview Q&A exchanges by asking
binary questions from skill ladders and requiring cited evidence.

The LLM is heavily constrained:
1. Must answer Yes/No/Insufficient
2. Must cite exact transcript excerpt
3. Must provide confidence score
4. Must give one-sentence reasoning
"""

import json
import logging
from typing import Any

from dotenv import load_dotenv

from core.llm_text import message_text
from scoring.models import (
    EvidenceCitation,
    EvidenceExtraction,
    LadderLevel,
    QAExchange,
    SkillLadder,
)

load_dotenv()


logger = logging.getLogger(__name__)

# Constrained prompt for evidence extraction
EVIDENCE_EXTRACTION_PROMPT = """You are evaluating interview evidence. You MUST answer in the EXACT format specified.

SKILL: {skill_name}
LEVEL: {level} ({level_description})
BINARY QUESTION: {binary_question}

EVIDENCE HINTS (what would indicate Yes):
{evidence_hints}

INTERVIEW EXCHANGE:
Interviewer: {interviewer_question}
Candidate: {candidate_response}

Does this exchange provide evidence that answers the binary question with YES?

RULES:
1. Answer ONLY "Yes", "No", or "Insufficient"
2. If Yes, you MUST quote the exact excerpt from the candidate's response
3. If No or Insufficient, evidence should be "N/A"
4. Confidence should reflect how clear the evidence is (0.0-1.0)
5. Reasoning must be ONE sentence explaining your answer

RESPOND IN EXACTLY THIS JSON FORMAT:
{{
    "answer": "Yes" | "No" | "Insufficient",
    "evidence": "[Exact quote from candidate response]" | "N/A",
    "confidence": 0.0-1.0,
    "reasoning": "One sentence explanation"
}}

IMPORTANT:
- "Yes" means clear, unambiguous evidence exists
- "No" means the response contradicts or clearly doesn't meet the level
- "Insufficient" means the response doesn't address this skill/level
- Be conservative - when in doubt, answer "Insufficient"
"""

# Batch extraction prompt for efficiency
BATCH_EXTRACTION_PROMPT = """You are evaluating interview evidence against multiple skill levels. For each skill/level combination, determine if the candidate's response provides evidence.

INTERVIEW EXCHANGE:
Interviewer: {interviewer_question}
Candidate: {candidate_response}

SKILLS TO EVALUATE:
{skills_to_evaluate}

For EACH skill/level, respond with:
- answer: "Yes", "No", or "Insufficient"
- evidence: Exact quote from candidate response (or "N/A")
- confidence: 0.0-1.0
- reasoning: One sentence

RESPOND IN THIS JSON FORMAT:
{{
    "extractions": [
        {{
            "skill_name": "...",
            "level": 1-5,
            "answer": "Yes" | "No" | "Insufficient",
            "evidence": "[Exact quote]" | "N/A",
            "confidence": 0.0-1.0,
            "reasoning": "..."
        }}
    ]
}}

RULES:
- Be conservative - "Insufficient" is preferred over uncertain "Yes"
- Evidence must be EXACT quotes, not paraphrasing
- Higher confidence for explicit, clear evidence
- Lower confidence for implicit or inferred evidence
"""


class EvidenceExtractor:
    """Extracts skill evidence from interview exchanges using constrained LLM.

    Uses binary questions from skill ladders and requires cited evidence
    for every determination.
    """

    def __init__(self, llm: Any | None = None, confidence_threshold: float = 0.7):
        """Initialize the evidence extractor.

        Args:
            llm: LangChain-compatible LLM instance
            confidence_threshold: Minimum confidence to confirm a level (default 0.7)
        """
        self._llm = llm
        self.confidence_threshold = confidence_threshold

    @property
    def llm(self) -> Any:
        """Lazy-load LLM instance."""
        if self._llm is None:
            from scoring.llm_client import scoring_llm

            self._llm = scoring_llm(temperature=0.0)
        return self._llm

    async def extract_single(
        self,
        exchange: QAExchange,
        skill_name: str,
        level: LadderLevel,
    ) -> EvidenceExtraction:
        """Extract evidence for a single skill/level from an exchange.

        Args:
            exchange: The Q&A exchange to analyze
            skill_name: Name of the skill being evaluated
            level: The ladder level to check

        Returns:
            EvidenceExtraction with answer, evidence, confidence, reasoning
        """
        level_descriptions = {
            1: "Awareness - mentioned or referenced",
            2: "Conceptual - explained what it is",
            3: "Practical - described real experience",
            4: "Problem-Solving - discussed challenges",
            5: "Mastery - demonstrated optimization/architecture",
        }

        prompt = EVIDENCE_EXTRACTION_PROMPT.format(
            skill_name=skill_name,
            level=level.level,
            level_description=level_descriptions.get(level.level, ""),
            binary_question=level.binary_question,
            evidence_hints="\n".join(f"- {hint}" for hint in level.evidence_hints),
            interviewer_question=exchange.interviewer_question,
            candidate_response=exchange.candidate_response,
        )

        try:
            response = await self.llm.ainvoke(prompt)
            content = message_text(response)

            parsed = self._extract_json(content)

            return EvidenceExtraction(
                skill_name=skill_name,
                level=level.level,
                answer=parsed.get("answer", "Insufficient"),
                evidence=parsed.get("evidence", "N/A"),
                confidence=float(parsed.get("confidence", 0.0)),
                reasoning=parsed.get("reasoning", "Failed to parse response"),
            )

        except Exception as e:
            logger.error(f"Error extracting evidence for {skill_name} L{level.level}: {e}")
            return EvidenceExtraction(
                skill_name=skill_name,
                level=level.level,
                answer="Insufficient",
                evidence="N/A",
                confidence=0.0,
                reasoning=f"Extraction error: {str(e)}",
            )

    async def extract_batch(
        self,
        exchange: QAExchange,
        ladders: dict[str, SkillLadder],
        current_levels: dict[str, int] | None = None,
    ) -> list[EvidenceExtraction]:
        """Extract evidence for multiple skills/levels from an exchange.

        Only evaluates levels that haven't been confirmed yet.

        Args:
            exchange: The Q&A exchange to analyze
            ladders: Dict of skill name to SkillLadder
            current_levels: Dict of skill name to current confirmed level (optional)

        Returns:
            List of EvidenceExtraction for each skill/level evaluated
        """
        if current_levels is None:
            current_levels = {}

        # Build list of skill/levels to evaluate
        skills_to_evaluate = []
        for skill_name, ladder in ladders.items():
            current = current_levels.get(skill_name, 0)
            # Only evaluate the next level (current + 1) and maybe current + 2
            for level in ladder.levels:
                if current < level.level <= current + 2:
                    skills_to_evaluate.append(
                        {
                            "skill_name": skill_name,
                            "level": level.level,
                            "binary_question": level.binary_question,
                            "evidence_hints": level.evidence_hints,
                        }
                    )

        if not skills_to_evaluate:
            logger.debug("No skills to evaluate - all at max level")
            return []

        # Format skills for prompt
        skills_text = "\n".join(
            f"- {s['skill_name']} Level {s['level']}: {s['binary_question']}\n"
            f"  Hints: {', '.join(s['evidence_hints'][:2])}"
            for s in skills_to_evaluate
        )

        prompt = BATCH_EXTRACTION_PROMPT.format(
            interviewer_question=exchange.interviewer_question,
            candidate_response=exchange.candidate_response,
            skills_to_evaluate=skills_text,
        )

        try:
            response = await self.llm.ainvoke(prompt)
            content = message_text(response)

            parsed = self._extract_json(content)
            extractions = []

            for item in parsed.get("extractions", []):
                extractions.append(
                    EvidenceExtraction(
                        skill_name=item.get("skill_name", "Unknown"),
                        level=int(item.get("level", 1)),
                        answer=item.get("answer", "Insufficient"),
                        evidence=item.get("evidence", "N/A"),
                        confidence=float(item.get("confidence", 0.0)),
                        reasoning=item.get("reasoning", ""),
                    )
                )

            return extractions

        except Exception as e:
            logger.error(f"Error in batch extraction: {e}")
            # Fall back to individual extractions
            logger.info("Falling back to individual extractions")
            extractions = []
            for skill_info in skills_to_evaluate:
                ladder = ladders[skill_info["skill_name"]]
                level = ladder.get_level(skill_info["level"])
                if level:
                    extraction = await self.extract_single(
                        exchange, skill_info["skill_name"], level
                    )
                    extractions.append(extraction)
            return extractions

    def create_citation_from_extraction(
        self, extraction: EvidenceExtraction, exchange: QAExchange
    ) -> EvidenceCitation | None:
        """Convert an extraction to a citation if it's a confirmed Yes.

        Args:
            extraction: The evidence extraction result
            exchange: The original Q&A exchange

        Returns:
            EvidenceCitation if extraction is Yes with sufficient confidence, else None
        """
        if extraction.answer != "Yes":
            return None

        if extraction.confidence < self.confidence_threshold:
            logger.debug(
                f"Skipping citation for {extraction.skill_name} L{extraction.level}: "
                f"confidence {extraction.confidence} < threshold {self.confidence_threshold}"
            )
            return None

        return EvidenceCitation(
            level=extraction.level,
            question_asked=exchange.interviewer_question,
            candidate_response=exchange.candidate_response,
            relevant_excerpt=extraction.evidence,
            confidence=extraction.confidence,
        )

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


# =============================================================================
# Utility Functions
# =============================================================================


def filter_confirmed_extractions(
    extractions: list[EvidenceExtraction],
    confidence_threshold: float = 0.7,
) -> list[EvidenceExtraction]:
    """Filter extractions to only confirmed Yes answers above threshold.

    Args:
        extractions: List of extractions to filter
        confidence_threshold: Minimum confidence for confirmation

    Returns:
        Filtered list of high-confidence Yes extractions
    """
    return [e for e in extractions if e.answer == "Yes" and e.confidence >= confidence_threshold]


def group_extractions_by_skill(
    extractions: list[EvidenceExtraction],
) -> dict[str, list[EvidenceExtraction]]:
    """Group extractions by skill name.

    Args:
        extractions: List of extractions

    Returns:
        Dict mapping skill name to list of extractions
    """
    grouped: dict[str, list[EvidenceExtraction]] = {}
    for extraction in extractions:
        if extraction.skill_name not in grouped:
            grouped[extraction.skill_name] = []
        grouped[extraction.skill_name].append(extraction)
    return grouped
