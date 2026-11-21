"""Niche skills detector using LLM for identifying exceptional candidate achievements.

Uses Gemini LLM to detect OSS programs (GSoC, LFX, Outreachy, MLH), hackathon wins,
and notable open source contributions from GitHub and resume data. This approach
replaces regex pattern matching for better accuracy and context extraction.
"""

import logging
from typing import Any

from brain.models.schemas import NicheSkillItem, NicheSkillsProfile

logger = logging.getLogger(__name__)


# =============================================================================
# LLM Detection Prompt
# =============================================================================

NICHE_DETECTION_PROMPT = """\
You are an expert at identifying exceptional achievements in software engineering profiles.

Analyze the following text from a candidate's profile to identify notable achievements.

## TEXT TO ANALYZE:
{text}

## ADDITIONAL CONTEXT:
- GitHub organizations the candidate belongs to: {orgs}
- High-star repositories (100+ stars): {repos}

## CATEGORIES TO DETECT:

### 1. OSS Programs (category: "oss_program")
Formal open source mentorship/fellowship programs including:
- Google Summer of Code (GSoC) - any year
- LFX Mentorship (Linux Foundation Mentorship)
- Outreachy
- MLH Fellowship (Major League Hacking)
- Rails Girls Summer of Code
- Season of Docs
- Google Season of Docs
- Open Source Promotion Plan (OSPP)
- FOSSASIA Codeheat
- Any other recognized open source programs

### 2. Hackathons & Competitions (category: "hackathon")
Competition achievements including:
- Hackathon wins, runner-up, finalist, top placements
- Coding competitions (ICPC, Google Code Jam, Meta Hacker Cup, etc.)
- Challenge victories (HackerRank, CodeChef, LeetCode contests)
- Startup weekends / demo days with placements

### 3. Notable OSS Contributions (category: "oss_contribution")
Significant open source involvement including:
- Core maintainer or significant contributor to well-known projects
- Accepted contributions to major open source projects
- Creator of popular/impactful open source tools
- Membership in prestigious open source organizations

## OUTPUT FORMAT:
For EACH achievement found, provide:
- category: One of "oss_program", "hackathon", or "oss_contribution"
- name: Full achievement name with year if available (e.g., "Google Summer of Code 2023")
- evidence: Direct quote or phrase from the text that supports this detection
- confidence: Float from 0.0 to 1.0 based on how clearly the achievement is stated
- year: Integer year if mentioned (null if not specified)
- context: Additional details like project name, organization, placement, or description

## IMPORTANT RULES:
1. ONLY include achievements with CLEAR evidence in the text
2. DO NOT hallucinate or infer achievements that are not explicitly mentioned
3. If someone mentions they "want to participate" or "applied to" a program,
   that is NOT a participation - skip it
4. Look for explicit phrases like "participated in", "selected for",
   "completed", "won", "finalist at"
5. Extract the year when mentioned (e.g., "GSoC 2023" -> year: 2023)
6. For hackathons, include the placement/achievement level in the name
7. If the text is empty or contains no achievements, return an empty array

Return a JSON object with an "achievements" array."""


# =============================================================================
# Main Detection Function
# =============================================================================


async def detect_niche_skills(
    github_bio: str | None = None,
    github_readme: str | None = None,
    github_orgs: list[dict[str, Any]] | None = None,
    github_repos: list[dict[str, Any]] | None = None,
    resume_text: str | None = None,
) -> NicheSkillsProfile:
    """Detect niche skills from candidate data sources using LLM.

    Uses Gemini LLM to analyze text sources and identify exceptional achievements
    that indicate high-potential candidates. Also uses deterministic detection
    for structured GitHub data (org memberships, high-star repos).

    Args:
        github_bio: GitHub user bio text
        github_readme: Content of profile README (username/username repo)
        github_orgs: List of GitHub orgs the user belongs to
        github_repos: List of user's repositories with star counts
        resume_text: Raw resume text

    Returns:
        NicheSkillsProfile with detected achievements
    """
    profile = NicheSkillsProfile()

    # Combine text sources for LLM analysis
    text_sources = {
        "GitHub bio": github_bio,
        "GitHub README": github_readme,
        "Resume": resume_text,
    }
    all_text = " ".join(filter(None, text_sources.values()))

    # Prepare structured context for LLM
    org_names = [org.get("login", "") for org in (github_orgs or []) if org.get("login")]
    high_star_repos = [
        f"{r.get('name')} ({r.get('stargazers_count', 0)} stars)"
        for r in (github_repos or [])
        if r.get("stargazers_count", 0) >= 100 and not r.get("fork", False)
    ]

    # LLM-based detection for text content
    if all_text.strip():
        try:
            llm_achievements = await _llm_detect_achievements(
                text=all_text,
                orgs=org_names,
                repos=high_star_repos,
            )

            # Parse LLM response into NicheSkillItems
            for achievement in llm_achievements:
                category = achievement.get("category", "")
                if category not in ("oss_program", "hackathon", "oss_contribution"):
                    logger.warning(f"Skipping invalid category: {category}")
                    continue

                # Build evidence string
                evidence = achievement.get("evidence", "LLM detection")
                context = achievement.get("context")
                if context:
                    evidence = f"{evidence} | Context: {context}"

                item = NicheSkillItem(
                    category=category,
                    name=achievement.get("name", "Unknown achievement"),
                    evidence=evidence,
                    confidence=min(max(achievement.get("confidence", 0.8), 0.0), 1.0),
                    year=achievement.get("year"),
                )

                if category == "oss_program":
                    profile.programs.append(item)
                elif category == "hackathon":
                    profile.hackathons.append(item)
                else:
                    profile.oss_contributions.append(item)

        except Exception as e:
            logger.error(f"LLM niche detection failed: {e}")
            # Continue with deterministic detection only

    # Deterministic detection for structured GitHub data
    # This catches notable org memberships and high-star repos
    # that may not be explicitly mentioned in bio/readme
    github_contributions = _detect_github_contributions(
        github_orgs or [],
        github_repos or [],
    )

    # Merge GitHub contributions, avoiding duplicates
    existing_names = {item.name.lower() for item in profile.oss_contributions}
    for item in github_contributions:
        if item.name.lower() not in existing_names:
            profile.oss_contributions.append(item)
            existing_names.add(item.name.lower())

    # Limit results to prevent overly long profiles
    profile.programs = profile.programs[:5]
    profile.hackathons = profile.hackathons[:5]
    profile.oss_contributions = profile.oss_contributions[:5]

    if not profile.is_empty():
        logger.info(
            f"Detected niche skills: {len(profile.programs)} programs, "
            f"{len(profile.hackathons)} hackathons, "
            f"{len(profile.oss_contributions)} OSS contributions"
        )

    return profile


# =============================================================================
# LLM Detection Helper
# =============================================================================


async def _llm_detect_achievements(
    text: str,
    orgs: list[str],
    repos: list[str],
) -> list[dict[str, Any]]:
    """Use LLM to detect achievements from text.

    Args:
        text: Combined text from all sources to analyze
        orgs: List of GitHub organization names
        repos: List of high-star repo descriptions

    Returns:
        List of achievement dictionaries with category, name, evidence, etc.
    """
    from brain.models.llm_pool import get_llm_pool

    pool = await get_llm_pool()
    client = pool.get_slow_client()

    # Prepare the prompt with context
    prompt = NICHE_DETECTION_PROMPT.format(
        text=text[:8000],  # Limit text length to avoid token issues
        orgs=", ".join(orgs) if orgs else "None found",
        repos=", ".join(repos[:10]) if repos else "None found",  # Limit repos list
    )

    try:
        response = await client.generate_with_schema(
            prompt=prompt,
            response_schema={
                "type": "object",
                "properties": {
                    "achievements": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "category": {
                                    "type": "string",
                                    "enum": ["oss_program", "hackathon", "oss_contribution"],
                                },
                                "name": {"type": "string"},
                                "evidence": {"type": "string"},
                                "confidence": {"type": "number"},
                                "year": {"type": ["integer", "null"]},
                                "context": {"type": ["string", "null"]},
                            },
                            "required": ["category", "name", "evidence", "confidence"],
                        },
                    }
                },
                "required": ["achievements"],
            },
        )

        achievements = response.get("achievements", [])
        logger.debug(f"LLM detected {len(achievements)} achievements")
        return achievements

    except Exception as e:
        logger.error(f"LLM achievement detection error: {e}")
        return []


# =============================================================================
# Deterministic GitHub Detection
# =============================================================================

# Notable organizations that indicate significant OSS involvement
NOTABLE_ORGS: set[str] = {
    "google",
    "microsoft",
    "facebook",
    "meta",
    "apple",
    "amazon",
    "netflix",
    "kubernetes",
    "apache",
    "mozilla",
    "linux",
    "cncf",
    "openai",
    "huggingface",
    "pytorch",
    "tensorflow",
    "django",
    "fastapi",
    "react",
    "vue",
    "angular",
    "nodejs",
    "golang",
    "rust-lang",
    "python",
    "numpy",
    "pandas-dev",
    "scikit-learn",
    "langchain-ai",
    "vercel",
    "supabase",
    "hashicorp",
    "elastic",
    "grafana",
    "prometheus",
    "istio",
    "envoyproxy",
}


def _detect_github_contributions(
    orgs: list[dict[str, Any]],
    repos: list[dict[str, Any]],
) -> list[NicheSkillItem]:
    """Detect notable OSS contributions from GitHub data.

    Uses deterministic rules for structured data:
    - Membership in notable organizations
    - Ownership of high-star repositories (100+ stars)

    Args:
        orgs: List of GitHub organizations the user belongs to
        repos: List of user's repositories with metadata

    Returns:
        List of NicheSkillItem for detected contributions
    """
    items = []

    # Check org memberships against notable orgs
    for org in orgs:
        org_login = org.get("login", "").lower()
        if org_login in NOTABLE_ORGS:
            items.append(
                NicheSkillItem(
                    category="oss_contribution",
                    name=f"Member of {org.get('login', 'notable org')}",
                    evidence="GitHub organization membership",
                    confidence=0.95,
                    url=f"https://github.com/{org.get('login', '')}",
                )
            )

    # Check for high-star repos (100+ stars = notable)
    for repo in repos:
        if repo.get("fork", False):
            continue  # Skip forked repos

        stars = repo.get("stargazers_count", 0)
        if stars >= 100:
            items.append(
                NicheSkillItem(
                    category="oss_contribution",
                    name=f"High-star repo: {repo.get('name', 'unknown')} ({stars} stars)",
                    evidence="GitHub repository",
                    confidence=0.9,
                    url=repo.get("html_url"),
                )
            )

    return items[:5]  # Limit to 5 OSS contribution entries
