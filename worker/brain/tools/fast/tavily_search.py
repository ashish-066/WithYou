"""Tavily search tool for fast brain.

Quick web search with filtered results (max 3) for low latency.
"""

import logging
import os
from datetime import datetime, timezone

from dotenv import load_dotenv

load_dotenv()

from brain.models.schemas import FilteredToolOutput, SearchResult, TavilySearchOutput
from brain.state import InterviewState

logger = logging.getLogger(__name__)


# =============================================================================
# Tool Implementation
# =============================================================================


async def tavily_search_tool(
    query: str,
    max_results: int = 3,
    state: InterviewState | None = None,
) -> FilteredToolOutput:
    """Perform a quick web search using Tavily API.

    This tool is designed for fast brain usage:
    - Maximum 3 results to minimize token usage
    - Quick search mode for low latency
    - Filtered output with only essential information

    Args:
        query: Search query string
        max_results: Maximum number of results (capped at 3)
        state: Optional interview state for context

    Returns:
        FilteredToolOutput containing TavilySearchOutput
    """
    try:
        # Import tavily client
        try:
            from tavily import TavilyClient
        except ImportError:
            logger.error("tavily-python not installed. Install with: pip install tavily-python")
            return FilteredToolOutput(
                success=False,
                data=None,
                confidence=0.0,
                source="tavily",
                error="tavily-python package not installed",
                timestamp=datetime.now(timezone.utc).isoformat(),
            )

        # Get API key
        api_key = os.getenv("TAVILY_API_KEY")
        if not api_key:
            return FilteredToolOutput(
                success=False,
                data=None,
                confidence=0.0,
                source="tavily",
                error="TAVILY_API_KEY environment variable not set",
                timestamp=datetime.now(timezone.utc).isoformat(),
            )

        # Initialize client and search
        client = TavilyClient(api_key=api_key)

        # Cap results at 3
        max_results = min(max_results, 3)

        # Perform search
        import time

        start_time = time.time()

        response = client.search(
            query=query,
            max_results=max_results,
            search_depth="basic",  # Use basic for speed
            include_answer=False,
            include_raw_content=False,
        )

        search_time_ms = int((time.time() - start_time) * 1000)

        # Parse results
        results = []
        for item in response.get("results", [])[:max_results]:
            results.append(
                SearchResult(
                    title=item.get("title", ""),
                    url=item.get("url", ""),
                    snippet=item.get("content", "")[:300],  # Limit snippet length
                    relevance_score=item.get("score", 0.5),
                )
            )

        output = TavilySearchOutput(
            query=query,
            results=results,
            total_found=len(response.get("results", [])),
            search_time_ms=search_time_ms,
        )

        return FilteredToolOutput(
            success=True,
            data=output.model_dump(),
            confidence=0.9 if results else 0.3,
            source="tavily",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    except Exception as e:
        logger.error(f"Tavily search error: {e}")
        return FilteredToolOutput(
            success=False,
            data=None,
            confidence=0.0,
            source="tavily",
            error=str(e),
            timestamp=datetime.now(timezone.utc).isoformat(),
        )


# =============================================================================
# Mock Implementation (for testing without API key)
# =============================================================================


async def tavily_search_mock(
    query: str,
    max_results: int = 3,
) -> FilteredToolOutput:
    """Mock Tavily search for testing."""
    output = TavilySearchOutput(
        query=query,
        results=[
            SearchResult(
                title=f"Mock Result for: {query}",
                url="https://example.com/mock",
                snippet=f"This is a mock search result for the query: {query}",
                relevance_score=0.8,
            )
        ],
        total_found=1,
        search_time_ms=50,
    )

    return FilteredToolOutput(
        success=True,
        data=output.model_dump(),
        confidence=0.5,
        source="tavily_mock",
        timestamp=datetime.now(timezone.utc).isoformat(),
    )
