"""Evidence-Based Skill Tree Scoring System.

This module implements a deterministic, explainable scoring system that:
1. Parses job descriptions to extract skills and generate depth ladders
2. Extracts evidence from interview conversations using constrained LLM calls
3. Builds skill trees that grow as evidence accumulates
4. Compares candidates using weighted Elo rankings

The system is designed to be:
- Deterministic: Same inputs produce same outputs
- Explainable: Every score has traceable evidence citations
- Fair: Skill transferability prevents penalizing equivalent experience
"""

from scoring.elo_system import EloSystem
from scoring.evidence_extractor import EvidenceExtractor
from scoring.integration import (
    ScoringIntegration,
    get_skill_summary,
    get_suggested_question,
    scoring_finalize_node,
    scoring_process_exchange_node,
)
from scoring.jd_parser import JDParser
from scoring.ladder_generator import SkillLadderGenerator
from scoring.models import (
    CandidateSkillTree,
    EloMatch,
    EloRating,
    EvidenceCitation,
    LadderLevel,
    RoleRequirements,
    SkillComparison,
    SkillLadder,
    SkillRequirement,
    SkillScore,
    SkillTransferability,
    SkillTreeNode,
    WeightedScore,
)
from scoring.question_selector import QuestionSelector
from scoring.score_calculator import ScoreCalculator
from scoring.tree_manager import SkillTreeManager

__all__ = [
    # Models
    "RoleRequirements",
    "SkillRequirement",
    "SkillLadder",
    "LadderLevel",
    "SkillTransferability",
    "SkillTreeNode",
    "EvidenceCitation",
    "CandidateSkillTree",
    "SkillScore",
    "WeightedScore",
    "EloRating",
    "EloMatch",
    "SkillComparison",
    # Services
    "JDParser",
    "SkillLadderGenerator",
    "EvidenceExtractor",
    "SkillTreeManager",
    "QuestionSelector",
    "ScoreCalculator",
    "EloSystem",
    # Integration
    "ScoringIntegration",
    "scoring_process_exchange_node",
    "scoring_finalize_node",
    "get_suggested_question",
    "get_skill_summary",
]
