"""Brain tools module.

This module exports all tools for use with the LangGraph interview agent
and dual-brain architecture.
"""

# Fast brain tools (upstream)
# Citation tools
from brain.tools.citation import (
    aggregate_citation_stats,
    get_all_citations,
    mark_citation,
)

# Crawler tools
from brain.tools.crawler import (
    crawl_github,
    crawl_linkedin,
    live_crawl,
    parse_resume,
)

# Evaluation tools
from brain.tools.evaluation import (
    generate_candidate_ranking_entry,
    generate_final_report,
    get_dashboard_data,
)
from brain.tools.fast import (
    conversation_tool,
    tavily_search_tool,
    timestamp_noter_tool,
    tool_decider,
)

# Rubric tools
from brain.tools.rubric import (
    calculate_rubric_score,
    fill_rubric_dimension,
    get_rubric_template,
)

# Search tools
from brain.tools.search import (
    simple_web_search,
    tavily_search,
)

# Slow brain tools (upstream)
from brain.tools.slow import (
    generate_analytics_report,
    generate_descriptive_report,
    profile_crawler_tool,
)

# Speech analysis tools
from brain.tools.speech import (
    analyze_speech_text,
    get_speech_confidence_resources,
)

# Export all tools as a list for easy binding to LLM
ALL_TOOLS = [
    # Fast brain
    conversation_tool,
    tavily_search_tool,
    timestamp_noter_tool,
    tool_decider,
    # Slow brain
    profile_crawler_tool,
    generate_analytics_report,
    generate_descriptive_report,
    # Crawler
    crawl_github,
    crawl_linkedin,
    parse_resume,
    live_crawl,
    # Speech
    analyze_speech_text,
    get_speech_confidence_resources,
    # Rubric
    get_rubric_template,
    fill_rubric_dimension,
    calculate_rubric_score,
    # Search
    tavily_search,
    simple_web_search,
    # Citation
    mark_citation,
    get_all_citations,
    aggregate_citation_stats,
    # Evaluation
    generate_final_report,
    get_dashboard_data,
    generate_candidate_ranking_entry,
]

__all__ = [
    # Fast brain tools
    "conversation_tool",
    "tavily_search_tool",
    "timestamp_noter_tool",
    "tool_decider",
    # Slow brain tools
    "profile_crawler_tool",
    "generate_descriptive_report",
    "generate_analytics_report",
    # Crawler
    "crawl_github",
    "crawl_linkedin",
    "parse_resume",
    "live_crawl",
    # Speech
    "analyze_speech_text",
    "get_speech_confidence_resources",
    # Rubric
    "get_rubric_template",
    "fill_rubric_dimension",
    "calculate_rubric_score",
    # Search
    "tavily_search",
    "simple_web_search",
    # Citation
    "mark_citation",
    "get_all_citations",
    "aggregate_citation_stats",
    # Evaluation
    "generate_final_report",
    "get_dashboard_data",
    "generate_candidate_ranking_entry",
    # All tools list
    "ALL_TOOLS",
]
