"""Speech confidence analysis tools.

This module provides tools for analyzing speech/transcript confidence
using filler word analysis and other heuristics.
"""

import json
import logging
import re

from langchain_core.tools import tool

logger = logging.getLogger(__name__)

# Common filler words and hedging phrases
FILLER_WORDS = [
    "um",
    "uh",
    "uhh",
    "umm",
    "er",
    "err",
    "ah",
    "ahh",
    "like",
    "you know",
    "basically",
    "actually",
    "literally",
    "sort of",
    "kind of",
    "i mean",
    "i guess",
    "i think",
    "maybe",
    "perhaps",
    "probably",
    "just",
    "really",
    "so yeah",
    "right",
    "okay so",
    "well",
]

# Hedging phrases that indicate uncertainty
HEDGING_PHRASES = [
    "i'm not sure",
    "i don't know",
    "i'm not certain",
    "it might be",
    "it could be",
    "possibly",
    "i believe",
    "i suppose",
    "if i remember correctly",
]


@tool
def analyze_speech_text(transcript: str) -> str:
    """
    Analyze transcript text to estimate speech confidence.
    Uses filler word frequency and sentence structure as proxies.

    Args:
        transcript: The text transcript to analyze.

    Returns:
        JSON string with confidence_score (0-1), filler_word_count,
        filler_words_list, and analysis notes.
    """
    try:
        if not transcript or not transcript.strip():
            return json.dumps({"error": "Empty transcript provided."})

        transcript_lower = transcript.lower()
        words = transcript_lower.split()
        word_count = len(words)

        if word_count == 0:
            return json.dumps({"error": "No words found in transcript."})

        # Count filler words
        filler_counts = {}
        total_filler_count = 0

        for filler in FILLER_WORDS:
            # Use word boundary regex for accurate matching
            pattern = r"\b" + re.escape(filler) + r"\b"
            matches = re.findall(pattern, transcript_lower)
            count = len(matches)
            if count > 0:
                filler_counts[filler] = count
                total_filler_count += count

        # Count hedging phrases
        hedging_counts = {}
        total_hedging_count = 0

        for hedge in HEDGING_PHRASES:
            count = transcript_lower.count(hedge)
            if count > 0:
                hedging_counts[hedge] = count
                total_hedging_count += count

        # Calculate filler ratio
        filler_ratio = total_filler_count / word_count

        # Calculate confidence score
        # Base confidence starts at 1.0
        # Subtract penalties for fillers and hedging
        confidence_score = 1.0

        # Filler penalty: each filler word reduces confidence
        # More than 5% filler words is concerning
        filler_penalty = min(filler_ratio * 4, 0.4)  # Max 0.4 penalty
        confidence_score -= filler_penalty

        # Hedging penalty
        hedging_ratio = total_hedging_count / max(word_count / 50, 1)  # Normalized
        hedging_penalty = min(hedging_ratio * 0.1, 0.2)  # Max 0.2 penalty
        confidence_score -= hedging_penalty

        # Clamp between 0 and 1
        confidence_score = max(0.0, min(1.0, confidence_score))

        # Generate analysis notes
        notes = []
        if filler_ratio > 0.05:
            notes.append("High filler word usage detected.")
        if filler_ratio > 0.1:
            notes.append("Very frequent use of filler words - may indicate nervousness.")
        if total_hedging_count > 3:
            notes.append("Multiple hedging phrases detected - may indicate uncertainty.")
        if confidence_score > 0.8:
            notes.append("Speech appears confident and clear.")
        elif confidence_score > 0.6:
            notes.append("Speech is moderately confident.")
        else:
            notes.append("Speech shows signs of uncertainty or nervousness.")

        # Speaking pace approximation (words per estimated minute)
        # Assume average speaking rate of 150 wpm
        # This is a rough approximation without actual audio timing
        estimated_speaking_pace = "normal"
        if word_count < 50:
            estimated_speaking_pace = "brief response"
        elif word_count > 300:
            estimated_speaking_pace = "detailed response"

        result = {
            "confidence_score": round(confidence_score, 3),
            "word_count": word_count,
            "filler_word_count": total_filler_count,
            "filler_ratio": round(filler_ratio, 4),
            "filler_words_found": filler_counts,
            "hedging_phrases_found": hedging_counts,
            "hedging_count": total_hedging_count,
            "estimated_speaking_pace": estimated_speaking_pace,
            "analysis_notes": notes,
        }

        return json.dumps(result, indent=2)

    except Exception as e:
        logger.exception(f"Error analyzing speech: {e}")
        return json.dumps({"error": f"Failed to analyze speech: {str(e)}"})


@tool
def get_speech_confidence_resources() -> str:
    """
    Return documentation and resources for calculating speech confidence.

    Returns:
        Markdown string with filler words list and scoring methodology.
    """
    resources = """
# Speech Confidence Analysis Methodology

## Overview
Speech confidence is estimated by analyzing the transcript for indicators
of uncertainty, nervousness, or lack of preparation.

## Filler Words Tracked
The following filler words are tracked and counted:
- **Vocal fillers**: um, uh, uhh, umm, er, err, ah, ahh
- **Verbal crutches**: like, you know, basically, actually, literally
- **Hedging words**: sort of, kind of, i mean, i guess, maybe, perhaps

## Hedging Phrases Tracked
- "I'm not sure", "I don't know", "I'm not certain"
- "It might be", "It could be", "Possibly"
- "I believe", "I suppose", "If I remember correctly"

## Scoring Methodology

### Base Score
- Starts at 1.0 (maximum confidence)

### Penalties Applied
1. **Filler Ratio Penalty**: `min(filler_ratio * 4, 0.4)`
   - Filler ratio = filler_count / total_words
   - Maximum penalty: 0.4

2. **Hedging Penalty**: `min(hedging_ratio * 0.1, 0.2)`
   - Maximum penalty: 0.2

### Score Interpretation
- **0.8 - 1.0**: Highly confident, clear communication
- **0.6 - 0.8**: Moderately confident
- **0.4 - 0.6**: Some uncertainty detected
- **0.0 - 0.4**: Significant uncertainty or nervousness

## Limitations
- This is a text-based analysis only
- Does not capture audio features (pitch, pace, volume)
- May not account for cultural or individual speaking patterns
- Filler words in quotes or examples are still counted

## Recommended Use
Use this score as one of several data points, not as a definitive measure.
Combine with rubric-based evaluation for comprehensive assessment.
"""

    return resources.strip()
