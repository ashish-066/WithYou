"""Claim checks must survive empty (None) profile fields.

Profile data comes from crawlers, resume parsing and the invite. Any field can be
present but None; claim checking runs when an interview ends, and a crash there
left the interview unconcluded with no report (staging, 2026-11-15).
"""

from brain.brains.slow_brain import _lower, _verify_single_claim

PROFILE_WITH_NULLS = {
    "github_data": {"bio": None, "top_languages": ["Python", None], "name": None},
    "linkedin_data": {
        "experience": [{"company": None, "title": None}],
        "education": [{"school": None, "degree": None}],
    },
    "resume_data": {
        "skills": ["Python", None],
        "companies": [None],
        "certifications": None,
        "experience": [{"company": None, "title": None}],
        "education": None,
    },
}


async def test_claims_against_a_profile_with_empty_fields_do_not_crash():
    for content in (
        "I worked at Google as a senior engineer",
        "I studied at MIT",
        "I know Python and Rust",
        "I have an AWS certification",
    ):
        result = await _verify_single_claim({"content": content, "claim_type": "experience"}, PROFILE_WITH_NULLS)
        assert result is not None


async def test_claim_without_content_does_not_crash():
    assert await _verify_single_claim({"content": None}, PROFILE_WITH_NULLS) is not None


def test_lower_handles_anything():
    assert _lower("AbC") == "abc"
    assert _lower(None) == ""
    assert _lower(3) == ""
