#!/usr/bin/env python3
"""Test script for brain tools.

Run this script to verify all tools work correctly:
    cd /home/hkx05/HASHLive/worker
    python -m brain.tools.test_tools
"""

import json
import sys

# Add parent directory to path for imports
sys.path.insert(0, "/home/hkx05/HASHLive/worker")


def test_crawler_tools():
    """Test crawler tools."""
    print("\n" + "=" * 50)
    print("Testing Crawler Tools")
    print("=" * 50)

    from brain.tools.crawler import crawl_github, live_crawl

    # Test crawl_github
    print("\n1. Testing crawl_github('torvalds')...")
    result = crawl_github.invoke("torvalds")
    data = json.loads(result)
    if "error" not in data:
        print(f"   ✓ Found user: {data.get('name')}")
        print(f"   ✓ Public repos: {data.get('public_repos')}")
        print(f"   ✓ Top languages: {[lang['language'] for lang in data.get('top_languages', [])]}")
    else:
        print(f"   ⚠ {data.get('error')}")

    # Test live_crawl
    print("\n2. Testing live_crawl('https://example.com')...")
    result = live_crawl.invoke("https://example.com")
    data = json.loads(result)
    if "error" not in data:
        print(f"   ✓ Title: {data.get('title')}")
        print(f"   ✓ Content length: {data.get('content_length')} chars")
    else:
        print(f"   ⚠ {data.get('error')}")


def test_speech_tools():
    """Test speech analysis tools."""
    print("\n" + "=" * 50)
    print("Testing Speech Tools")
    print("=" * 50)

    from brain.tools.speech import analyze_speech_text, get_speech_confidence_resources

    # Test analyze_speech_text
    print("\n1. Testing analyze_speech_text with filler words...")
    transcript = "Well um I think like basically you know I worked on this project and um it was like really challenging."
    result = analyze_speech_text.invoke(transcript)
    data = json.loads(result)
    if "error" not in data:
        print(f"   ✓ Confidence score: {data.get('confidence_score')}")
        print(f"   ✓ Filler word count: {data.get('filler_word_count')}")
        print(f"   ✓ Filler words found: {list(data.get('filler_words_found', {}).keys())}")
    else:
        print(f"   ⚠ {data.get('error')}")

    # Test clean speech
    print("\n2. Testing analyze_speech_text with clean speech...")
    clean = "I led the migration project at my previous company. We improved performance by 40%."
    result = analyze_speech_text.invoke(clean)
    data = json.loads(result)
    print(f"   ✓ Confidence score: {data.get('confidence_score')}")

    # Test resources
    print("\n3. Testing get_speech_confidence_resources...")
    resources = get_speech_confidence_resources.invoke("")
    print(f"   ✓ Resources returned ({len(resources)} chars)")


def test_rubric_tools():
    """Test rubric tools."""
    print("\n" + "=" * 50)
    print("Testing Rubric Tools")
    print("=" * 50)

    from brain.tools.rubric import (
        calculate_rubric_score,
        fill_rubric_dimension,
        get_rubric_template,
    )

    # Test get_rubric_template
    print("\n1. Testing get_rubric_template('Backend Engineer')...")
    rubric_json = get_rubric_template.invoke("Backend Engineer")
    rubric = json.loads(rubric_json)
    if "error" not in rubric:
        print(f"   ✓ Role: {rubric.get('role')}")
        print(f"   ✓ Dimensions: {[d['name'] for d in rubric.get('dimensions', [])]}")
    else:
        print(f"   ⚠ {rubric.get('error')}")

    # Test fill_rubric_dimension
    print("\n2. Testing fill_rubric_dimension...")
    filled = fill_rubric_dimension.invoke(
        {
            "rubric_json": rubric_json,
            "dimension_name": "Technical Depth",
            "score": 4,
            "reasoning": "Strong knowledge of backend technologies",
        }
    )
    data = json.loads(filled)
    if "error" not in data:
        for dim in data.get("dimensions", []):
            if dim.get("name") == "Technical Depth":
                print(f"   ✓ Score set: {dim.get('score')}")
                print(f"   ✓ Reasoning: {dim.get('reasoning')[:50]}...")
    else:
        print(f"   ⚠ {data.get('error')}")

    # Fill more dimensions and calculate score
    print("\n3. Testing calculate_rubric_score...")
    # Fill all dimensions
    for dim_name, score in [
        ("System Design", 4),
        ("Problem Solving", 5),
        ("Communication", 4),
        ("Experience Fit", 3),
    ]:
        filled = fill_rubric_dimension.invoke(
            {
                "rubric_json": filled,
                "dimension_name": dim_name,
                "score": score,
                "reasoning": f"Good {dim_name.lower()}",
            }
        )

    score_result = calculate_rubric_score.invoke(filled)
    score_data = json.loads(score_result)
    if "error" not in score_data:
        print(
            f"   ✓ Overall score: {score_data.get('overall_score')}/{score_data.get('max_possible')}"
        )
        print(f"   ✓ Percentage: {score_data.get('percentage')}%")
        print(f"   ✓ Recommendation: {score_data.get('recommendation')}")
    else:
        print(f"   ⚠ {score_data.get('error')}")


def test_search_tools():
    """Test search tools."""
    print("\n" + "=" * 50)
    print("Testing Search Tools")
    print("=" * 50)

    from brain.tools.search import simple_web_search, tavily_search

    # Test tavily_search (will likely fail without API key)
    print("\n1. Testing tavily_search...")
    result = tavily_search.invoke("Python FastAPI tutorial")
    data = json.loads(result)
    if "error" in data:
        print(f"   ⚠ {data.get('error')} (expected without API key)")
    else:
        print(f"   ✓ Found {len(data.get('results', []))} results")

    # Test simple_web_search
    print("\n2. Testing simple_web_search...")
    result = simple_web_search.invoke("kubernetes best practices")
    data = json.loads(result)
    print(f"   ✓ Suggested followup: {data.get('suggested_followup')[:50]}...")


def test_citation_tools():
    """Test citation tools."""
    print("\n" + "=" * 50)
    print("Testing Citation Tools")
    print("=" * 50)

    from brain.tools.citation import aggregate_citation_stats, get_all_citations, mark_citation

    # Create some citations
    print("\n1. Testing mark_citation...")
    citations = []

    c1 = mark_citation.invoke(
        {
            "claim_id": "claim-001",
            "transcript_excerpt": "I led the Kubernetes migration project",
            "timestamp_seconds": 120.5,
            "verdict": "verified",
        }
    )
    citations.append(json.loads(c1))
    print(f"   ✓ Citation 1 created: {json.loads(c1).get('verdict')}")

    c2 = mark_citation.invoke(
        {
            "claim_id": "claim-002",
            "transcript_excerpt": "We handled 10k requests per second",
            "timestamp_seconds": 185.0,
            "verdict": "unverified",
        }
    )
    citations.append(json.loads(c2))
    print(f"   ✓ Citation 2 created: {json.loads(c2).get('verdict')}")

    # Test get_all_citations
    print("\n2. Testing get_all_citations...")
    citations_json = json.dumps(citations)
    formatted = get_all_citations.invoke(citations_json)
    print(f"   ✓ Formatted output ({len(formatted)} chars)")

    # Test aggregate_citation_stats
    print("\n3. Testing aggregate_citation_stats...")
    stats = aggregate_citation_stats.invoke(citations_json)
    stats_data = json.loads(stats)
    print(f"   ✓ Total citations: {stats_data.get('total_citations')}")
    print(f"   ✓ Trust score: {stats_data.get('trust_score')}")


def test_evaluation_tools():
    """Test evaluation tools."""
    print("\n" + "=" * 50)
    print("Testing Evaluation Tools")
    print("=" * 50)

    from brain.tools.evaluation import (
        generate_candidate_ranking_entry,
        generate_final_report,
        get_dashboard_data,
    )

    # Create test data
    rubric = {
        "role": "Backend Engineer",
        "dimensions": [
            {"name": "Technical Depth", "max_score": 5, "score": 4, "reasoning": "Strong"},
            {"name": "Problem Solving", "max_score": 5, "score": 5, "reasoning": "Excellent"},
            {"name": "Communication", "max_score": 5, "score": 4, "reasoning": "Clear"},
        ],
    }
    citations = [{"claim_id": "c1", "verdict": "verified"}]

    # Test generate_final_report
    print("\n1. Testing generate_final_report...")
    report = generate_final_report.invoke(
        {
            "candidate_name": "John Doe",
            "role": "Backend Engineer",
            "rubric_json": json.dumps(rubric),
            "citations_json": json.dumps(citations),
            "trust_score": 0.85,
            "summary_notes": "Strong candidate with good technical skills.",
        }
    )
    print(f"   ✓ Report generated ({len(report)} chars)")
    print(f"   ✓ Contains 'Overall Assessment': {'Overall Assessment' in report}")

    # Test get_dashboard_data
    print("\n2. Testing get_dashboard_data...")
    dashboard = get_dashboard_data.invoke(
        {
            "rubric_json": json.dumps(rubric),
            "trust_score": 0.85,
            "speech_confidence": 0.78,
        }
    )
    data = json.loads(dashboard)
    print(f"   ✓ Rubric chart labels: {data.get('rubric_chart', {}).get('labels')}")
    print(f"   ✓ Summary: {data.get('summary')}")

    # Test generate_candidate_ranking_entry
    print("\n3. Testing generate_candidate_ranking_entry...")
    entry = generate_candidate_ranking_entry.invoke(
        {
            "candidate_id": "cand-123",
            "candidate_name": "John Doe",
            "role": "Backend Engineer",
            "rubric_json": json.dumps(rubric),
            "trust_score": 0.85,
            "speech_confidence": 0.78,
        }
    )
    entry_data = json.loads(entry)
    print(f"   ✓ Composite score: {entry_data.get('composite_score')}")
    print(f"   ✓ Status: {entry_data.get('status')}")


def main():
    """Run all tests."""
    print("\n" + "#" * 60)
    print("# HASHLive Brain Tools Test Suite")
    print("#" * 60)

    try:
        test_crawler_tools()
        test_speech_tools()
        test_rubric_tools()
        test_search_tools()
        test_citation_tools()
        test_evaluation_tools()

        print("\n" + "=" * 50)
        print("All tests completed!")
        print("=" * 50 + "\n")

    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback

        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
