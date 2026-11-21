"""Crawler tools for extracting candidate information.

This module provides tools for crawling GitHub profiles, LinkedIn profiles,
parsing resumes, and doing live web crawls during interviews.
"""

import json
import logging
import os
import re
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup
from langchain_core.tools import tool

logger = logging.getLogger(__name__)

# GitHub API base URL
GITHUB_API_BASE = "https://api.github.com"


@tool
def crawl_github(github_username: str) -> str:
    """
    Crawl a public GitHub profile and extract repositories, languages, and stats.

    Args:
        github_username: The GitHub username to crawl.

    Returns:
        JSON string with repos (name, description, language, stars, forks),
        top languages, and total public repo count.
    """
    try:
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "HASHLive-Interview-Agent",
        }

        # Use token if available for higher rate limits
        github_token = os.getenv("GITHUB_TOKEN")
        if github_token:
            headers["Authorization"] = f"token {github_token}"

        with httpx.Client(timeout=30.0) as client:
            # Fetch user profile
            user_response = client.get(
                f"{GITHUB_API_BASE}/users/{github_username}",
                headers=headers,
            )

            if user_response.status_code == 404:
                return json.dumps({"error": f"GitHub user '{github_username}' not found."})
            elif user_response.status_code == 403:
                return json.dumps({"error": "GitHub API rate limit exceeded. Try again later."})
            elif user_response.status_code != 200:
                return json.dumps({"error": f"GitHub API error: {user_response.status_code}"})

            user_data = user_response.json()

            # Fetch repositories (non-forked, owned by user)
            repos_response = client.get(
                f"{GITHUB_API_BASE}/users/{github_username}/repos",
                params={"type": "owner", "per_page": 100, "sort": "updated"},
                headers=headers,
            )

            if repos_response.status_code != 200:
                return json.dumps({"error": f"Failed to fetch repos: {repos_response.status_code}"})

            repos_data = repos_response.json()

            # Filter out forked repos and extract relevant info
            repos = []
            language_stats = {}

            for repo in repos_data:
                if repo.get("fork"):
                    continue

                repo_info = {
                    "name": repo.get("name"),
                    "description": repo.get("description") or "",
                    "language": repo.get("language") or "Unknown",
                    "stars": repo.get("stargazers_count", 0),
                    "forks": repo.get("forks_count", 0),
                    "url": repo.get("html_url"),
                }
                repos.append(repo_info)

                # Aggregate language stats
                lang = repo.get("language")
                if lang:
                    language_stats[lang] = language_stats.get(lang, 0) + 1

            # Sort languages by frequency
            top_languages = sorted(language_stats.items(), key=lambda x: x[1], reverse=True)[:5]

            result = {
                "username": github_username,
                "name": user_data.get("name") or github_username,
                "bio": user_data.get("bio") or "",
                "public_repos": user_data.get("public_repos", 0),
                "followers": user_data.get("followers", 0),
                "following": user_data.get("following", 0),
                "repos": repos[:20],  # Limit to top 20 repos
                "top_languages": [
                    {"language": lang, "count": count} for lang, count in top_languages
                ],
                "profile_url": user_data.get("html_url"),
            }

            return json.dumps(result, indent=2)

    except httpx.TimeoutException:
        return json.dumps({"error": "GitHub API request timed out."})
    except Exception as e:
        logger.exception(f"Error crawling GitHub: {e}")
        return json.dumps({"error": f"Failed to crawl GitHub: {str(e)}"})


@tool
def crawl_linkedin(linkedin_url: str) -> str:
    """
    Crawl a public LinkedIn profile and extract work history and skills.

    Note: LinkedIn scraping requires authentication or a third-party API.
    This implementation checks for PROXYCURL_API_KEY environment variable.

    Args:
        linkedin_url: The full LinkedIn profile URL.

    Returns:
        JSON string with work history and skills, or error message if
        scraping is not configured.
    """
    try:
        # Validate URL
        parsed = urlparse(linkedin_url)
        if "linkedin.com" not in parsed.netloc:
            return json.dumps({"error": "Invalid LinkedIn URL. Must be a linkedin.com URL."})

        # Check for Proxycurl API key
        proxycurl_key = os.getenv("PROXYCURL_API_KEY")

        if proxycurl_key:
            # Use Proxycurl API
            headers = {"Authorization": f"Bearer {proxycurl_key}"}

            with httpx.Client(timeout=30.0) as client:
                response = client.get(
                    "https://nubela.co/proxycurl/api/v2/linkedin",
                    params={"url": linkedin_url},
                    headers=headers,
                )

                if response.status_code == 200:
                    data = response.json()
                    result = {
                        "name": data.get("full_name", ""),
                        "headline": data.get("headline", ""),
                        "summary": data.get("summary", ""),
                        "location": data.get("city", "") + ", " + data.get("country_full_name", ""),
                        "experiences": [
                            {
                                "title": exp.get("title", ""),
                                "company": exp.get("company", ""),
                                "duration": exp.get("duration", ""),
                                "description": exp.get("description", ""),
                            }
                            for exp in data.get("experiences", [])[:5]
                        ],
                        "skills": data.get("skills", [])[:15],
                        "education": [
                            {
                                "school": edu.get("school", ""),
                                "degree": edu.get("degree_name", ""),
                                "field": edu.get("field_of_study", ""),
                            }
                            for edu in data.get("education", [])[:3]
                        ],
                    }
                    return json.dumps(result, indent=2)
                elif response.status_code == 404:
                    return json.dumps({"error": "LinkedIn profile not found."})
                else:
                    return json.dumps({"error": f"Proxycurl API error: {response.status_code}"})

        # If no API key, return a placeholder message
        return json.dumps(
            {
                "warning": "LinkedIn scraping not fully configured.",
                "message": "Set PROXYCURL_API_KEY environment variable for full LinkedIn data.",
                "url": linkedin_url,
                "extracted": {
                    "note": "Basic extraction attempted. For reliable data, use Proxycurl API."
                },
            }
        )

    except httpx.TimeoutException:
        return json.dumps({"error": "LinkedIn request timed out."})
    except Exception as e:
        logger.exception(f"Error crawling LinkedIn: {e}")
        return json.dumps({"error": f"Failed to crawl LinkedIn: {str(e)}"})


@tool
def parse_resume(resume_url_or_path: str) -> str:
    """
    Parse a resume (PDF or DOCX) and extract structured text and skills.

    Args:
        resume_url_or_path: URL or local path to the resume file.

    Returns:
        JSON string with extracted text and identified skills.
    """
    try:
        file_content = None
        file_extension = None

        # Check if it's a URL or local path
        if resume_url_or_path.startswith(("http://", "https://")):
            # Download the file
            with httpx.Client(timeout=60.0) as client:
                response = client.get(resume_url_or_path)
                if response.status_code != 200:
                    return json.dumps(
                        {"error": f"Failed to download resume: HTTP {response.status_code}"}
                    )
                file_content = response.content

            # Determine file type from URL or content-type
            content_type = response.headers.get("content-type", "")
            if "pdf" in content_type or resume_url_or_path.lower().endswith(".pdf"):
                file_extension = "pdf"
            elif "docx" in content_type or resume_url_or_path.lower().endswith(".docx"):
                file_extension = "docx"
            else:
                file_extension = "pdf"  # Default assumption
        else:
            # Local file
            if not os.path.exists(resume_url_or_path):
                return json.dumps({"error": f"File not found: {resume_url_or_path}"})

            with open(resume_url_or_path, "rb") as f:
                file_content = f.read()

            if resume_url_or_path.lower().endswith(".pdf"):
                file_extension = "pdf"
            elif resume_url_or_path.lower().endswith(".docx"):
                file_extension = "docx"
            else:
                return json.dumps({"error": "Unsupported file format. Use PDF or DOCX."})

        # Extract text based on file type
        extracted_text = ""

        if file_extension == "pdf":
            try:
                import io

                import pypdf

                pdf_reader = pypdf.PdfReader(io.BytesIO(file_content))
                for page in pdf_reader.pages:
                    extracted_text += page.extract_text() or ""
            except ImportError:
                return json.dumps({"error": "pypdf not installed. Run: pip install pypdf"})

        elif file_extension == "docx":
            try:
                import io

                import docx

                doc = docx.Document(io.BytesIO(file_content))
                for para in doc.paragraphs:
                    extracted_text += para.text + "\n"
            except ImportError:
                return json.dumps(
                    {"error": "python-docx not installed. Run: pip install python-docx"}
                )

        # Extract skills using simple pattern matching
        skill_patterns = [
            r"Python",
            r"JavaScript",
            r"TypeScript",
            r"Java",
            r"C\+\+",
            r"C#",
            r"React",
            r"Angular",
            r"Vue",
            r"Node\.js",
            r"Django",
            r"Flask",
            r"FastAPI",
            r"AWS",
            r"Azure",
            r"GCP",
            r"Docker",
            r"Kubernetes",
            r"K8s",
            r"PostgreSQL",
            r"MySQL",
            r"MongoDB",
            r"Redis",
            r"Machine Learning",
            r"Deep Learning",
            r"TensorFlow",
            r"PyTorch",
            r"Git",
            r"CI/CD",
            r"Jenkins",
            r"GitHub Actions",
            r"REST API",
            r"GraphQL",
            r"Microservices",
            r"Agile",
            r"Scrum",
            r"Jira",
        ]

        found_skills = []
        for pattern in skill_patterns:
            if re.search(pattern, extracted_text, re.IGNORECASE):
                found_skills.append(pattern.replace(r"\+", "+").replace(r"\.", "."))

        result = {
            "text": extracted_text[:5000],  # Limit text length
            "text_length": len(extracted_text),
            "extracted_skills": list(set(found_skills)),
            "source": resume_url_or_path,
        }

        return json.dumps(result, indent=2)

    except Exception as e:
        logger.exception(f"Error parsing resume: {e}")
        return json.dumps({"error": f"Failed to parse resume: {str(e)}"})


@tool
def live_crawl(url: str) -> str:
    """
    Quickly fetch and extract main content from a URL.
    Use when candidate mentions a link during interview.

    Args:
        url: The URL to crawl.

    Returns:
        Extracted main content as text (max 2000 chars).
    """
    try:
        # Validate URL
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            return json.dumps({"error": "Invalid URL format."})

        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; HASHLive-Bot/1.0)",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }

        with httpx.Client(timeout=15.0, follow_redirects=True) as client:
            response = client.get(url, headers=headers)

            if response.status_code != 200:
                return json.dumps({"error": f"Failed to fetch URL: HTTP {response.status_code}"})

            content_type = response.headers.get("content-type", "")
            if "text/html" not in content_type:
                return json.dumps(
                    {
                        "url": url,
                        "content_type": content_type,
                        "note": "Non-HTML content. Cannot extract text.",
                    }
                )

            # Parse HTML
            soup = BeautifulSoup(response.text, "html.parser")

            # Remove script and style elements
            for element in soup(["script", "style", "nav", "header", "footer", "aside"]):
                element.decompose()

            # Try to find main content
            main_content = None
            for selector in ["main", "article", '[role="main"]', ".content", "#content"]:
                main_content = soup.select_one(selector)
                if main_content:
                    break

            if not main_content:
                main_content = soup.body if soup.body else soup

            # Extract text
            text = main_content.get_text(separator="\n", strip=True)

            # Clean up whitespace
            text = re.sub(r"\n{3,}", "\n\n", text)
            text = text[:2000]  # Limit to 2000 chars

            # Get page title
            title = soup.title.string if soup.title else ""

            result = {
                "url": url,
                "title": title.strip() if title else "",
                "content": text,
                "content_length": len(text),
            }

            return json.dumps(result, indent=2)

    except httpx.TimeoutException:
        return json.dumps({"error": "Request timed out."})
    except Exception as e:
        logger.exception(f"Error in live crawl: {e}")
        return json.dumps({"error": f"Failed to crawl URL: {str(e)}"})
