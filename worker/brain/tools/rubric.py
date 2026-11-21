"""Rubric management tools for interview evaluation.

This module provides tools for creating, managing, and filling
evaluation rubrics during interviews.
"""

import json
import logging

from langchain_core.tools import tool

logger = logging.getLogger(__name__)

# Role-specific rubric templates
RUBRIC_TEMPLATES = {
    "frontend": {
        "role": "Frontend Engineer",
        "dimensions": [
            {
                "name": "Technical Depth",
                "description": "Knowledge of frontend technologies (HTML, CSS, JS, frameworks)",
                "max_score": 5,
                "score": None,
                "reasoning": None,
            },
            {
                "name": "Problem Solving",
                "description": "Ability to break down problems and design solutions",
                "max_score": 5,
                "score": None,
                "reasoning": None,
            },
            {
                "name": "Communication",
                "description": "Clarity of explanation and articulation of ideas",
                "max_score": 5,
                "score": None,
                "reasoning": None,
            },
            {
                "name": "Experience Fit",
                "description": "Relevance of past experience to the role",
                "max_score": 5,
                "score": None,
                "reasoning": None,
            },
            {
                "name": "UI/UX Awareness",
                "description": "Understanding of design principles and user experience",
                "max_score": 5,
                "score": None,
                "reasoning": None,
            },
        ],
    },
    "backend": {
        "role": "Backend Engineer",
        "dimensions": [
            {
                "name": "Technical Depth",
                "description": "Knowledge of backend technologies, databases, APIs",
                "max_score": 5,
                "score": None,
                "reasoning": None,
            },
            {
                "name": "System Design",
                "description": "Ability to design scalable and maintainable systems",
                "max_score": 5,
                "score": None,
                "reasoning": None,
            },
            {
                "name": "Problem Solving",
                "description": "Algorithmic thinking and debugging skills",
                "max_score": 5,
                "score": None,
                "reasoning": None,
            },
            {
                "name": "Communication",
                "description": "Clarity of explanation and articulation of ideas",
                "max_score": 5,
                "score": None,
                "reasoning": None,
            },
            {
                "name": "Experience Fit",
                "description": "Relevance of past experience to the role",
                "max_score": 5,
                "score": None,
                "reasoning": None,
            },
        ],
    },
    "devops": {
        "role": "DevOps Engineer",
        "dimensions": [
            {
                "name": "Infrastructure Knowledge",
                "description": "Understanding of cloud platforms, containers, orchestration",
                "max_score": 5,
                "score": None,
                "reasoning": None,
            },
            {
                "name": "CI/CD Expertise",
                "description": "Experience with pipelines, automation, deployment strategies",
                "max_score": 5,
                "score": None,
                "reasoning": None,
            },
            {
                "name": "Problem Solving",
                "description": "Debugging, troubleshooting, incident response",
                "max_score": 5,
                "score": None,
                "reasoning": None,
            },
            {
                "name": "Communication",
                "description": "Clarity of explanation and articulation of ideas",
                "max_score": 5,
                "score": None,
                "reasoning": None,
            },
            {
                "name": "Security Awareness",
                "description": "Understanding of security best practices",
                "max_score": 5,
                "score": None,
                "reasoning": None,
            },
        ],
    },
    "generic": {
        "role": "Software Engineer",
        "dimensions": [
            {
                "name": "Technical Depth",
                "description": "Overall technical knowledge and expertise",
                "max_score": 5,
                "score": None,
                "reasoning": None,
            },
            {
                "name": "Problem Solving",
                "description": "Ability to analyze and solve complex problems",
                "max_score": 5,
                "score": None,
                "reasoning": None,
            },
            {
                "name": "Communication",
                "description": "Clarity of explanation and articulation of ideas",
                "max_score": 5,
                "score": None,
                "reasoning": None,
            },
            {
                "name": "Experience Fit",
                "description": "Relevance of past experience to the role",
                "max_score": 5,
                "score": None,
                "reasoning": None,
            },
            {
                "name": "Cultural Alignment",
                "description": "Fit with team values and work style",
                "max_score": 5,
                "score": None,
                "reasoning": None,
            },
        ],
    },
}


@tool
def get_rubric_template(role: str) -> str:
    """
    Get an empty rubric template for a given role.

    Args:
        role: The job role (e.g., "Frontend Engineer", "Backend Engineer", "DevOps").

    Returns:
        JSON string with rubric dimensions, each having name, description,
        max_score, score (null), and reasoning (null).
    """
    try:
        role_lower = role.lower().strip()

        # Match role to template
        template_key = "generic"
        if "frontend" in role_lower or "front-end" in role_lower or "front end" in role_lower:
            template_key = "frontend"
        elif "backend" in role_lower or "back-end" in role_lower or "back end" in role_lower:
            template_key = "backend"
        elif (
            "devops" in role_lower
            or "dev ops" in role_lower
            or "sre" in role_lower
            or "infrastructure" in role_lower
        ):
            template_key = "devops"

        template = RUBRIC_TEMPLATES[template_key].copy()
        template["dimensions"] = [dim.copy() for dim in template["dimensions"]]

        return json.dumps(template, indent=2)

    except Exception as e:
        logger.exception(f"Error getting rubric template: {e}")
        return json.dumps({"error": f"Failed to get rubric template: {str(e)}"})


@tool
def fill_rubric_dimension(rubric_json: str, dimension_name: str, score: int, reasoning: str) -> str:
    """
    Fill a specific dimension in the rubric.

    Args:
        rubric_json: The current rubric as JSON string.
        dimension_name: The dimension to fill (e.g., "Technical Depth").
        score: Score (1-5).
        reasoning: Reasoning for the score.

    Returns:
        Updated rubric as JSON string.
    """
    try:
        rubric = json.loads(rubric_json)

        # Validate score
        if not isinstance(score, int) or score < 1 or score > 5:
            return json.dumps({"error": "Score must be an integer between 1 and 5."})

        # Find and update the dimension
        dimension_found = False
        for dim in rubric.get("dimensions", []):
            if dim.get("name", "").lower() == dimension_name.lower():
                dim["score"] = score
                dim["reasoning"] = reasoning
                dimension_found = True
                break

        if not dimension_found:
            return json.dumps(
                {
                    "error": f"Dimension '{dimension_name}' not found in rubric.",
                    "available_dimensions": [d.get("name") for d in rubric.get("dimensions", [])],
                }
            )

        return json.dumps(rubric, indent=2)

    except json.JSONDecodeError:
        return json.dumps({"error": "Invalid JSON provided for rubric."})
    except Exception as e:
        logger.exception(f"Error filling rubric dimension: {e}")
        return json.dumps({"error": f"Failed to fill rubric dimension: {str(e)}"})


@tool
def calculate_rubric_score(rubric_json: str) -> str:
    """
    Calculate the overall score from a filled rubric.

    Args:
        rubric_json: The filled rubric as JSON string.

    Returns:
        JSON string with overall_score, max_possible, percentage,
        and recommendation.
    """
    try:
        rubric = json.loads(rubric_json)
        dimensions = rubric.get("dimensions", [])

        if not dimensions:
            return json.dumps({"error": "No dimensions found in rubric."})

        total_score = 0
        max_possible = 0
        filled_count = 0

        for dim in dimensions:
            max_possible += dim.get("max_score", 5)
            if dim.get("score") is not None:
                total_score += dim["score"]
                filled_count += 1

        if filled_count == 0:
            return json.dumps({"error": "No dimensions have been scored yet."})

        percentage = (total_score / max_possible) * 100

        # Determine recommendation
        if percentage >= 80:
            recommendation = "strong_yes"
        elif percentage >= 65:
            recommendation = "yes"
        elif percentage >= 50:
            recommendation = "maybe"
        elif percentage >= 35:
            recommendation = "no"
        else:
            recommendation = "strong_no"

        result = {
            "overall_score": total_score,
            "max_possible": max_possible,
            "percentage": round(percentage, 1),
            "dimensions_filled": filled_count,
            "dimensions_total": len(dimensions),
            "recommendation": recommendation,
        }

        return json.dumps(result, indent=2)

    except json.JSONDecodeError:
        return json.dumps({"error": "Invalid JSON provided for rubric."})
    except Exception as e:
        logger.exception(f"Error calculating rubric score: {e}")
        return json.dumps({"error": f"Failed to calculate rubric score: {str(e)}"})
