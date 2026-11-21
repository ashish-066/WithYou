"""The learner asking, by voice, to change language ("మలయాళంలో చెప్పు", "speak English").

Deterministic on purpose: told "Reply in Telugu" by the session, the model would
agree to switch ("సరే, ఇప్పుడు మలయాళంలో చెబుతాను") and then carry on in Telugu.
The processor changes the session's language first; the voice agent then speaks
and listens in it (it follows the script of the reply).
"""

from __future__ import annotations

import re

# A language name used as "in <language>": Telugu "-లో", Malayalam "-ത്തിൽ/-ിൽ",
# English "in/speak/switch to/... <language>" or "<language> please"
_REQUESTS = {
    "ml-IN": [
        r"మలయాళం\s*లో", r"మలయాళంలో",
        r"മലയാളത്തിൽ",
        r"மலையாளத்தில்", r"मलयालम\s*में",
        r"\b(in|speak|talk|use|switch to|reply in|answer in)\s+malayalam\b", r"\bmalayalam\s+please\b",
    ],
    "te-IN": [
        r"తెలుగు\s*లో", r"తెలుగులో",
        r"തെലുങ്കിൽ", r"തെലുഗിൽ",
        r"தெலுங்கில்", r"तेलुगु\s*में",
        r"\b(in|speak|talk|use|switch to|reply in|answer in)\s+telugu\b", r"\btelugu\s+please\b",
    ],
    "ta-IN": [
        r"தமிழ்\s*ல", r"தமிழில்", r"तमिल\s*में",
        r"\b(in|speak|talk|use|switch to|reply in|answer in)\s+tamil\b", r"\btamil\s+please\b",
    ],
    "hi-IN": [
        r"हिंदी\s*में", r"हिन्दी\s*में", r"ஹிந்தி\s*ல", r"హిందీ\s*లో", r"ഹിന്ദിയിൽ",
        r"\b(in|speak|talk|use|switch to|reply in|answer in)\s+hindi\b", r"\bhindi\s+please\b",
    ],
    "en-IN": [
        r"இங்கிலீஷ்\s*ல", r"ஆங்கிலத்தில்", r"इंग्लिश\s*में", r"अंग्रेज़ी\s*में", r"अंग्रेजी\s*में",
        r"ఇంగ్లీష్\s*లో", r"ఇంగ్లీషులో", r"ఇంగ్లిష్\s*లో",
        r"ഇംഗ്ലീഷിൽ",
        r"\b(in|speak|talk|use|switch to|reply in|answer in)\s+english\b", r"\benglish\s+please\b",
    ],
}
_COMPILED = {lang: [re.compile(p, re.IGNORECASE) for p in pats] for lang, pats in _REQUESTS.items()}


def requested_language(text: str, current: str | None = None) -> str | None:
    """The language the learner asks to switch to, or None (also None for the current one)."""
    asked = [lang for lang, pats in _COMPILED.items() if any(p.search(text) for p in pats)]
    if len(asked) != 1 or asked[0] == current:
        return None  # nothing asked, or ambiguous ("Telugu or Malayalam?")
    return asked[0]
