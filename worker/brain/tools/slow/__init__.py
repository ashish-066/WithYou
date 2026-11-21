"""Slow brain tools package."""

from brain.tools.slow.niche_detector import detect_niche_skills
from brain.tools.slow.profile_crawler import profile_crawler_tool
from brain.tools.slow.report_generator import (
    generate_analytics_report,
    generate_descriptive_report,
)

__all__ = [
    "profile_crawler_tool",
    "generate_descriptive_report",
    "generate_analytics_report",
    "detect_niche_skills",
]
