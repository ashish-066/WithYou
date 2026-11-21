"""Profile crawler tool for slow brain.

Crawls GitHub and LinkedIn profiles for candidate verification.
"""

import asyncio
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any

from brain.models.schemas import (
    FilteredToolOutput,
    GitHubProfile,
    LinkedInProfile,
    NicheSkillsProfile,
    ProfileCrawlResult,
    ResumeData,
    ResumeExperience,
)
from brain.state import InterviewState
from brain.tools.safe_fetch import fetch_pages
from brain.tools.slow.niche_detector import detect_niche_skills

logger = logging.getLogger(__name__)


# =============================================================================
# LLM-Based Resume Extraction Schema
# =============================================================================

RESUME_EXTRACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {
            "type": "string",
            "description": "Full name of the candidate",
        },
        "email": {
            "type": "string",
            "description": "Email address",
        },
        "phone": {
            "type": "string",
            "description": "Phone number",
        },
        "skills": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Technical skills, languages, frameworks, tools",
        },
        "experience": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "company": {"type": "string"},
                    "title": {"type": "string"},
                    "start_year": {"type": "integer"},
                    "end_year": {"type": "integer"},
                    "team_size": {"type": "integer"},
                    "description": {"type": "string"},
                },
                "required": ["company"],
            },
            "description": "Work experience entries",
        },
        "education": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Education entries (e.g., 'BS Computer Science, Stanford')",
        },
        "certifications": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Certifications (e.g., AWS Solutions Architect, OSCP, CKA)",
        },
        "experience_years": {
            "type": "integer",
            "description": "Total years of professional experience",
        },
        "publications": {
            "type": "integer",
            "description": "Number of publications or papers mentioned",
        },
    },
    "required": ["skills", "experience", "education", "certifications"],
}


# =============================================================================
# Profile Crawler Implementation
# =============================================================================


async def profile_crawler_tool(
    github_url: str | None = None,
    linkedin_url: str | None = None,
    resume_url: str | None = None,
    state: InterviewState | None = None,
    other_links: list[str] | None = None,
) -> FilteredToolOutput:
    """Crawl candidate profiles from GitHub and LinkedIn.

    This tool is designed for slow brain usage:
    - Deep crawling of GitHub repositories
    - LinkedIn profile extraction
    - Resume parsing (from URL or state.candidate_resume_text)
    - Skills and experience extraction
    - Niche skills detection (GSoC, hackathons, notable OSS)

    Args:
        github_url: GitHub profile URL
        linkedin_url: LinkedIn profile URL
        resume_url: URL to resume file
        state: Optional interview state for context (may contain candidate_resume_text)

    Returns:
        FilteredToolOutput containing ProfileCrawlResult with niche_skills
    """
    errors: list[str] = []
    github_data: GitHubProfile | None = None
    linkedin_data: LinkedInProfile | None = None
    resume_data: ResumeData | None = None
    linkedin_export: ResumeData | None = None
    links: list[dict] = []
    niche_skills: NicheSkillsProfile | None = None
    skills_extracted: set[str] = set()

    try:
        # Run crawlers in parallel
        tasks: list[tuple[str, Any]] = []

        if github_url:
            tasks.append(("github", _crawl_github(github_url)))
        # LinkedIn blocks automated reading: only its "Save to PDF" export is
        # used (parsed like a resume); a bare LinkedIn link adds nothing
        linkedin_text = state.get("candidate_linkedin_text") if state else None
        if linkedin_text:
            tasks.append(("linkedin_export", _extract_resume_data_llm(linkedin_text)))
        if other_links:
            tasks.append(("links", fetch_pages(list(other_links))))

        # Check for resume text from state first (OCR'd/pre-extracted text)
        resume_text_from_state = state.get("candidate_resume_text") if state else None
        if resume_text_from_state:
            logger.info(
                f"[RESUME_EXTRACT] Using candidate_resume_text from state "
                f"({len(resume_text_from_state)} chars)"
            )
            tasks.append(("resume", _extract_resume_data_llm(resume_text_from_state)))
        elif resume_url:
            # Fallback: download and parse from URL
            tasks.append(("resume", _parse_resume(resume_url)))

        if tasks:
            results = await asyncio.gather(
                *[task[1] for task in tasks],
                return_exceptions=True,
            )

            for (source, _), result in zip(tasks, results):
                if isinstance(result, Exception):
                    errors.append(f"{source}: {str(result)}")
                    continue

                if source == "github" and result:
                    # GitHub now returns tuple: (GitHubProfile, NicheSkillsProfile)
                    if isinstance(result, tuple):
                        github_data, niche_skills = result
                        if github_data:
                            skills_extracted.update(github_data.top_languages)
                    else:
                        # Fallback for old return type
                        github_data = result
                        if hasattr(result, "top_languages"):
                            skills_extracted.update(result.top_languages)
                elif source == "linkedin_export" and result:
                    linkedin_export = result
                    if hasattr(result, "skills"):
                        skills_extracted.update(result.skills)
                elif source == "links" and result:
                    links = result
                elif source == "resume" and result:
                    resume_data = result
                    if hasattr(result, "skills"):
                        skills_extracted.update(result.skills)

        # Detect additional niche skills from resume text if available
        niche_source_text = resume_text_from_state or (
            _extract_resume_text(resume_data) if resume_data else None
        )
        if niche_source_text and not niche_skills:
            # Create niche skills profile from resume if GitHub didn't provide one
            niche_skills = await detect_niche_skills(resume_text=niche_source_text)
        elif niche_source_text and niche_skills:
            # Merge resume niche skills with GitHub niche skills
            resume_niche = await detect_niche_skills(resume_text=niche_source_text)
            niche_skills = _merge_niche_skills(niche_skills, resume_niche)

        # Calculate experience years (prefer resume_data if available)
        experience_years = None
        if resume_data and resume_data.experience_years:
            experience_years = resume_data.experience_years
        elif linkedin_export and linkedin_export.experience_years:
            experience_years = linkedin_export.experience_years
        else:
            experience_years = _calculate_experience_years(linkedin_data, resume_data)

        result = ProfileCrawlResult(
            github=github_data,
            linkedin=linkedin_data,
            resume=resume_data,
            linkedin_export=linkedin_export,
            links=links,
            niche_skills=niche_skills,
            skills_extracted=list(skills_extracted)[:30],  # Limit skills
            experience_years=experience_years,
            errors=errors,
        )

        # Log extracted resume data for debugging
        if resume_data:
            logger.info(
                f"[RESUME_EXTRACT] Extracted: "
                f"skills={len(resume_data.skills)}, "
                f"companies={resume_data.companies}, "
                f"certifications={resume_data.certifications}, "
                f"experience_years={resume_data.experience_years}"
            )

        return FilteredToolOutput(
            success=len(errors) == 0 or bool(github_data or resume_data or linkedin_export or links),
            data=result.model_dump(),
            confidence=_calculate_confidence(result),
            source="profile_crawler",
            timestamp=datetime.now(timezone.utc).isoformat(),
            error="; ".join(errors) if errors else None,
        )

    except Exception as e:
        logger.error(f"Profile crawler error: {e}")
        return FilteredToolOutput(
            success=False,
            data=None,
            confidence=0.0,
            source="profile_crawler",
            error=str(e),
            timestamp=datetime.now(timezone.utc).isoformat(),
        )


# =============================================================================
# GitHub Crawler
# =============================================================================


async def _crawl_github(url: str) -> tuple[GitHubProfile | None, NicheSkillsProfile | None]:
    """Crawl GitHub profile using the GitHub API with enhanced niche detection.

    Fetches user profile, repositories, organizations, and profile README
    to detect niche skills like GSoC participation, hackathon wins, and
    notable OSS contributions.

    Args:
        url: GitHub profile URL or username

    Returns:
        Tuple of (GitHubProfile, NicheSkillsProfile) or (None, None) on failure
    """
    try:
        import httpx

        # Extract username from URL
        username = _extract_github_username(url)
        if not username:
            logger.warning(f"Could not extract GitHub username from: {url}")
            return None, None

        # Use GitHub API
        api_url = f"https://api.github.com/users/{username}"
        headers = {"Accept": "application/vnd.github.v3+json"}

        # Add token if available
        token = os.getenv("GITHUB_TOKEN")
        if token:
            headers["Authorization"] = f"token {token}"

        async with httpx.AsyncClient() as client:
            # Get user profile
            response = await client.get(api_url, headers=headers, timeout=10.0)
            if response.status_code != 200:
                logger.warning(f"GitHub API returned {response.status_code} for {username}")
                return None, None

            data = response.json()

            # Get repos sorted by stars to find notable ones
            repos_url = f"https://api.github.com/users/{username}/repos?sort=stars&per_page=20"
            repos_response = await client.get(repos_url, headers=headers, timeout=10.0)

            repos = []
            top_languages: set[str] = set()
            pinned_repos = []

            if repos_response.status_code == 200:
                repos = repos_response.json()
                for repo in repos[:6]:
                    if repo.get("language"):
                        top_languages.add(repo["language"])
                    pinned_repos.append(repo.get("name", ""))

            # NEW: Get user organizations
            orgs = []
            orgs_url = f"https://api.github.com/users/{username}/orgs"
            orgs_response = await client.get(orgs_url, headers=headers, timeout=10.0)
            if orgs_response.status_code == 200:
                orgs = orgs_response.json()

            # NEW: Get profile README (username/username repo)
            readme_content = None
            readme_url = f"https://api.github.com/repos/{username}/{username}/readme"
            readme_headers = {**headers, "Accept": "application/vnd.github.v3.raw"}
            readme_response = await client.get(readme_url, headers=readme_headers, timeout=10.0)
            if readme_response.status_code == 200:
                readme_content = readme_response.text

            # Build GitHub profile
            github_profile = GitHubProfile(
                username=username,
                name=data.get("name"),
                bio=data.get("bio"),
                public_repos=data.get("public_repos", 0),
                followers=data.get("followers", 0),
                following=data.get("following", 0),
                top_languages=list(top_languages)[:10],
                pinned_repos=pinned_repos[:6],
                profile_url=url,
                repos=_repo_details(repos),
            )

            # NEW: Detect niche skills from GitHub data
            niche_skills = await detect_niche_skills(
                github_bio=data.get("bio"),
                github_readme=readme_content,
                github_orgs=orgs,
                github_repos=repos,
            )

            return github_profile, niche_skills

    except Exception as e:
        logger.error(f"GitHub crawl error: {e}")
        raise


def _extract_github_username(url: str) -> str | None:
    """Extract username from GitHub URL."""
    patterns = [
        r"github\.com/([^/\?]+)",
        r"^([a-zA-Z0-9_-]+)$",  # Just username
    ]

    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)

    return None


# =============================================================================
# LinkedIn Crawler
# =============================================================================


def _repo_details(repos: list[dict]) -> list[dict]:
    """The candidate's own repositories first, by stars: what the interviewer asks about."""
    own = [r for r in repos if not r.get("fork")] + [r for r in repos if r.get("fork")]
    return [
        {
            "name": r.get("name", ""),
            "description": (r.get("description") or "")[:300],
            "language": r.get("language"),
            "stars": r.get("stargazers_count", 0),
            "pushed_at": r.get("pushed_at"),
            "fork": bool(r.get("fork")),
            "url": r.get("html_url"),
        }
        for r in own[:10]
    ]


# =============================================================================
# Resume Parser
# =============================================================================


async def _parse_resume(url: str) -> ResumeData | None:
    """Parse resume from URL.

    Supports PDF and DOCX formats.
    """
    try:
        import httpx

        # Download resume
        async with httpx.AsyncClient() as client:
            response = await client.get(url, timeout=30.0, follow_redirects=True)
            if response.status_code != 200:
                logger.warning(f"Failed to download resume: {response.status_code}")
                return None

            content = response.content
            content_type = response.headers.get("content-type", "")

        # Parse based on content type
        if "pdf" in content_type or url.lower().endswith(".pdf"):
            return await _parse_pdf_resume(content)
        elif "word" in content_type or url.lower().endswith((".docx", ".doc")):
            return await _parse_docx_resume(content)
        else:
            logger.warning(f"Unsupported resume format: {content_type}")
            return None

    except Exception as e:
        logger.error(f"Resume parse error: {e}")
        raise


async def _parse_pdf_resume(content: bytes) -> ResumeData | None:
    """Parse PDF resume content."""
    try:
        # Try to import pypdf
        try:
            from io import BytesIO

            from pypdf import PdfReader

            reader = PdfReader(BytesIO(content))
            text = ""
            for page in reader.pages:
                text += page.extract_text() or ""

            return _extract_resume_data(text)

        except ImportError:
            logger.warning("pypdf not installed. Install with: pip install pypdf")
            return None

    except Exception as e:
        logger.error(f"PDF parse error: {e}")
        return None


async def _parse_docx_resume(content: bytes) -> ResumeData | None:
    """Parse DOCX resume content."""
    try:
        try:
            from io import BytesIO

            from docx import Document

            doc = Document(BytesIO(content))
            text = "\n".join([para.text for para in doc.paragraphs])

            return _extract_resume_data(text)

        except ImportError:
            logger.warning("python-docx not installed. Install with: pip install python-docx")
            return None

    except Exception as e:
        logger.error(f"DOCX parse error: {e}")
        return None


def _extract_resume_data(text: str) -> ResumeData:
    """Extract structured data from resume text."""
    # Simple extraction - in production, use LLM or specialized parser

    # Extract email
    email_match = re.search(r"[\w.-]+@[\w.-]+\.\w+", text)
    email = email_match.group(0) if email_match else None

    # Extract phone
    phone_match = re.search(r"[\+]?[(]?[0-9]{1,3}[)]?[-\s\.]?[0-9]{3}[-\s\.]?[0-9]{4,6}", text)
    phone = phone_match.group(0) if phone_match else None

    # Extract skills (look for common skill keywords)
    skill_keywords = [
        "Python",
        "JavaScript",
        "TypeScript",
        "Java",
        "C++",
        "Go",
        "Rust",
        "React",
        "Vue",
        "Angular",
        "Node.js",
        "Django",
        "FastAPI",
        "Flask",
        "AWS",
        "GCP",
        "Azure",
        "Docker",
        "Kubernetes",
        "SQL",
        "MongoDB",
        "PostgreSQL",
        "Redis",
        "GraphQL",
        "REST",
        "Git",
        "Linux",
        "Machine Learning",
        "AI",
        "TensorFlow",
        "PyTorch",
    ]

    found_skills = [skill for skill in skill_keywords if skill.lower() in text.lower()]

    return ResumeData(
        email=email,
        phone=phone,
        skills=found_skills,
        experience=[],
        education=[],
        projects=[],
        companies=[],
        certifications=[],
    )


async def _extract_resume_data_llm(text: str) -> ResumeData:
    """Extract structured data from resume text using LLM.

    Uses the slow brain LLM pool for accurate, structured extraction of:
    - Skills, companies, certifications
    - Team sizes, experience years, publications
    - Education entries

    Args:
        text: Raw resume text (from OCR or file parsing)

    Returns:
        ResumeData with populated verification fields
    """
    from brain.models.llm_pool import get_llm_pool

    try:
        pool = await get_llm_pool()
        client = pool.get_slow_client()

        # Truncate very long resumes to avoid token limits
        max_chars = 8000
        if len(text) > max_chars:
            text = text[:max_chars] + "\n\n[Resume truncated for processing]"

        prompt = f"""Extract structured information from this resume text for candidate verification.

RESUME TEXT:
---
{text}
---

INSTRUCTIONS:
1. Extract ALL technical skills mentioned (languages, frameworks, tools, platforms)
2. For each work experience, extract:
   - Company name (normalize: "Google LLC" -> "Google")
   - Job title
   - Start and end years (if mentioned)
   - Team size (look for phrases like "led team of 10", "managed 5 engineers")
   - Brief description
3. Extract education entries as strings (e.g., "BS Computer Science, Stanford University")
4. Extract ALL certifications with their full names (e.g., "AWS Solutions Architect", "OSCP", "CKA", "CISSP")
5. Calculate total years of professional experience from work history dates
6. Count publications/papers if mentioned

BE CONSERVATIVE:
- Only extract what is EXPLICITLY stated in the resume
- If uncertain about a value, omit it rather than guess
- For team_size, only include if explicitly mentioned with a number

Return a JSON object with the following structure:
{{
    "name": "Candidate Name or null",
    "email": "email@example.com or null",
    "phone": "phone number or null",
    "skills": ["Python", "JavaScript", "AWS", ...],
    "experience": [
        {{
            "company": "Company Name",
            "title": "Job Title or null",
            "start_year": 2020,
            "end_year": 2023,
            "team_size": 5,
            "description": "Brief description or null"
        }}
    ],
    "education": ["BS Computer Science, Stanford University", ...],
    "certifications": ["AWS Solutions Architect", "OSCP", ...],
    "experience_years": 5,
    "publications": 3
}}"""

        # Use structured output for reliable JSON parsing
        result = await client.generate_with_schema(
            prompt=prompt,
            response_schema=RESUME_EXTRACTION_SCHEMA,
        )

        logger.info(f"[RESUME_EXTRACT] LLM extraction completed: {list(result.keys())}")

        # Parse experience into ResumeExperience objects
        experience_entries = []
        companies = []
        max_team_size = None

        for exp in result.get("experience", []):
            if isinstance(exp, dict) and exp.get("company"):
                company = exp["company"]
                companies.append(company)

                # Track max team size
                if exp.get("team_size"):
                    if max_team_size is None or exp["team_size"] > max_team_size:
                        max_team_size = exp["team_size"]

                experience_entries.append(
                    ResumeExperience(
                        company=company,
                        title=exp.get("title"),
                        start_year=exp.get("start_year"),
                        end_year=exp.get("end_year"),
                        team_size=exp.get("team_size"),
                        description=exp.get("description"),
                    )
                )

        # Build education summary for verification matching
        education_list = result.get("education", [])
        education_summary = " | ".join(education_list) if education_list else None

        resume_data = ResumeData(
            name=result.get("name"),
            email=result.get("email"),
            phone=result.get("phone"),
            skills=result.get("skills", []),
            experience=experience_entries,
            education=education_list,
            certifications=result.get("certifications", []),
            companies=companies,
            experience_years=result.get("experience_years"),
            max_team_size=max_team_size,
            publications=result.get("publications"),
            education_summary=education_summary,
            projects=[],
        )

        logger.info(
            f"[RESUME_EXTRACT] Final ResumeData: "
            f"skills={len(resume_data.skills)}, "
            f"experience={len(resume_data.experience)}, "
            f"companies={resume_data.companies}, "
            f"certifications={resume_data.certifications}, "
            f"experience_years={resume_data.experience_years}, "
            f"max_team_size={resume_data.max_team_size}"
        )

        return resume_data

    except Exception as e:
        logger.error(f"[RESUME_EXTRACT] LLM extraction failed: {e}, falling back to regex")
        # Fallback to basic regex extraction
        return _extract_resume_data(text)


# =============================================================================
# Helper Functions
# =============================================================================


def _calculate_experience_years(
    linkedin: LinkedInProfile | None,
    resume: ResumeData | None,
) -> int | None:
    """Calculate total years of experience."""
    # This would analyze work history dates in production
    # For now, return None to indicate unknown
    return None


def _calculate_confidence(result: ProfileCrawlResult) -> float:
    """Calculate confidence score based on data completeness."""
    score = 0.0
    total = 3.0

    if result.github and result.github.public_repos > 0:
        score += 1.0
    if result.linkedin and result.linkedin.name:
        score += 1.0
    if result.resume and (result.resume.email or result.resume.skills):
        score += 1.0

    return score / total if total > 0 else 0.0


def _extract_resume_text(resume_data: ResumeData) -> str:
    """Extract searchable text from resume data for niche skills detection.

    Args:
        resume_data: Parsed resume data

    Returns:
        Concatenated text from resume fields
    """
    parts = []

    if resume_data.name:
        parts.append(resume_data.name)
    if resume_data.skills:
        parts.append(" ".join(resume_data.skills))
    if resume_data.certifications:
        parts.append(" ".join(resume_data.certifications))

    # Extract text from experience entries (handle both dict and ResumeExperience)
    for exp in resume_data.experience:
        if isinstance(exp, dict):
            for value in exp.values():
                if isinstance(value, str):
                    parts.append(value)
        elif hasattr(exp, "company"):
            # ResumeExperience object
            if exp.company:
                parts.append(exp.company)
            if exp.title:
                parts.append(exp.title)
            if exp.description:
                parts.append(exp.description)

    # Extract text from education entries (now a list of strings)
    for edu in resume_data.education:
        if isinstance(edu, str):
            parts.append(edu)
        elif isinstance(edu, dict):
            for value in edu.values():
                if isinstance(value, str):
                    parts.append(value)

    # Extract text from projects
    for proj in resume_data.projects:
        if isinstance(proj, dict):
            for value in proj.values():
                if isinstance(value, str):
                    parts.append(value)

    return " ".join(parts)


def _merge_niche_skills(
    primary: NicheSkillsProfile,
    secondary: NicheSkillsProfile,
) -> NicheSkillsProfile:
    """Merge two NicheSkillsProfile instances, avoiding duplicates.

    Args:
        primary: Primary profile (usually from GitHub)
        secondary: Secondary profile (usually from resume)

    Returns:
        Merged NicheSkillsProfile with deduplicated achievements
    """
    # Create sets of existing achievement names for deduplication
    existing_programs = {item.name for item in primary.programs}
    existing_hackathons = {item.name for item in primary.hackathons}
    existing_oss = {item.name for item in primary.oss_contributions}

    # Merge programs
    merged_programs = list(primary.programs)
    for item in secondary.programs:
        if item.name not in existing_programs:
            merged_programs.append(item)

    # Merge hackathons
    merged_hackathons = list(primary.hackathons)
    for item in secondary.hackathons:
        if item.name not in existing_hackathons:
            merged_hackathons.append(item)

    # Merge OSS contributions
    merged_oss = list(primary.oss_contributions)
    for item in secondary.oss_contributions:
        if item.name not in existing_oss:
            merged_oss.append(item)

    return NicheSkillsProfile(
        programs=merged_programs,
        hackathons=merged_hackathons,
        oss_contributions=merged_oss,
    )
