"""Which language the buddy speaks: Malayalam, Telugu or English.

The learner can switch at any time. Speech recognition (Sarvam, language=auto)
reports the language of each turn; the brain answers in it; and the voice picks
the language of each reply from its script, so it always matches the words.
"""

from __future__ import annotations

SUPPORTED = ("ml-IN", "te-IN", "en-IN")

# Unicode blocks of the scripts we speak
_SCRIPTS = {
    "te-IN": range(0x0C00, 0x0C80),  # Telugu
    "ml-IN": range(0x0D00, 0x0D80),  # Malayalam
}

GREETINGS = {
    "ml-IN": (
        "ഹായ്! ഞാൻ നിന്റെ പഠന കൂട്ടുകാരനാണ്. ഇന്ന് നമുക്ക് എന്ത് പഠിക്കാം? "
        "ഒരു വിഷയം പറയൂ, അല്ലെങ്കിൽ ചുമ്മാ ഒരു ഹായ് പറഞ്ഞാലും മതി."
    ),
    "te-IN": (
        "హాయ్! నేను నీ స్టడీ బడ్డీని. ఈ రోజు మనం ఏమి నేర్చుకుందాం? "
        "ఏదైనా టాపిక్ చెప్పు, లేదా ఊరికే హాయ్ చెప్పినా చాలు."
    ),
    "en-IN": (
        "Hey there! I'm your study buddy. What shall we study today? "
        "Tell me a topic, or just say hi and we'll figure it out together."
    ),
}

# Short lines the agent says itself (agents/interview_monitor.py keys)
NUDGES = {
    "repeat_offer": {
        "ml-IN": "തിരക്കൊന്നുമില്ല! ഞാൻ ഒന്നുകൂടി പറയണോ, അതോ ഒരു ചെറിയ ക്ലൂ തരട്ടെ?",
        "te-IN": "తొందరేమీ లేదు! నేను మళ్ళీ చెప్పనా, లేక చిన్న హింట్ ఇవ్వనా?",
        "en-IN": "No rush! Want me to say that again, or shall I give you a little hint?",
    },
}


def normalize(code: object | None) -> str | None:
    """A speech-recognition language ("te", "te-IN", "ml-in") as one of SUPPORTED."""
    if not code:
        return None
    prefix = str(code).strip().lower().split("-")[0]
    return next((lang for lang in SUPPORTED if lang.lower().startswith(prefix + "-")), None)


def language_of(text: str, default: str = "en-IN") -> str:
    """The language to speak `text` in, from its script (Latin-only text is English)."""
    counts = {lang: sum(1 for ch in text if ord(ch) in block) for lang, block in _SCRIPTS.items()}
    lang, n = max(counts.items(), key=lambda kv: kv[1])
    if n:
        return lang
    return "en-IN" if any(ch.isalpha() for ch in text) else default


def greeting(language: str | None) -> str:
    return GREETINGS.get(language or "", GREETINGS["ml-IN"])


def nudge(key: str, language: str | None) -> str:
    lines = NUDGES.get(key, {})
    return lines.get(language or "", lines.get("en-IN", ""))
