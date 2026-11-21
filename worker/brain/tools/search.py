"""Web search tools using Tavily API.

This module provides tools for searching the web for additional context
during interviews.
"""

import json
import logging
import os

from langchain_core.tools import tool

logger = logging.getLogger(__name__)


@tool
def tavily_search(query: str) -> str:
    """
    Search the web using Tavily API and return summarized results.

    Args:
        query: The search query.

    Returns:
        Summarized search results as text, or error message if API not configured.
    """
    try:
        if not query or not query.strip():
            return json.dumps({"error": "Empty search query provided."})

        api_key = os.getenv("TAVILY_API_KEY")

        if not api_key:
            return json.dumps(
                {
                    "error": "Tavily API key not configured.",
                    "message": "Set TAVILY_API_KEY environment variable to enable web search.",
                    "query": query,
                }
            )

        # Try using tavily-python library
        try:
            from tavily import TavilyClient

            client = TavilyClient(api_key=api_key)
            response = client.search(
                query=query,
                search_depth="basic",
                max_results=5,
            )

            results = []
            for result in response.get("results", []):
                results.append(
                    {
                        "title": result.get("title", ""),
                        "url": result.get("url", ""),
                        "content": result.get("content", "")[:500],  # Truncate long content
                    }
                )

            return json.dumps(
                {
                    "query": query,
                    "results": results,
                    "answer": response.get("answer", ""),
                },
                indent=2,
            )

        except ImportError:
            # Fall back to direct HTTP request
            import httpx

            with httpx.Client(timeout=30.0) as client:
                response = client.post(
                    "https://api.tavily.com/search",
                    json={
                        "api_key": api_key,
                        "query": query,
                        "search_depth": "basic",
                        "max_results": 5,
                    },
                )

                if response.status_code != 200:
                    return json.dumps(
                        {
                            "error": f"Tavily API error: {response.status_code}",
                            "details": response.text[:200],
                        }
                    )

                data = response.json()

                results = []
                for result in data.get("results", []):
                    results.append(
                        {
                            "title": result.get("title", ""),
                            "url": result.get("url", ""),
                            "content": result.get("content", "")[:500],
                        }
                    )

                return json.dumps(
                    {
                        "query": query,
                        "results": results,
                        "answer": data.get("answer", ""),
                    },
                    indent=2,
                )

    except Exception as e:
        logger.exception(f"Error in Tavily search: {e}")
        return json.dumps({"error": f"Search failed: {str(e)}"})


@tool
def simple_web_search(query: str) -> str:
    """
    A fallback search tool that provides guidance when web search is not available.

    Args:
        query: The search query.

    Returns:
        Guidance message for the interviewer.
    """
    return json.dumps(
        {
            "query": query,
            "note": "Web search API not available. Consider asking the candidate directly for more details.",
            "suggested_followup": f"Can you tell me more about {query}?",
        },
        indent=2,
    )
