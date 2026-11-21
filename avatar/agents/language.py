"""Which language the buddy speaks: Malayalam, Telugu or English.

Speech recognition is locked to the session's language (Sarvam's "auto" mode
heard Telugu as Kannada on a real mic). The learner switches with the language
buttons in the room, or by asking the buddy: when a reply comes in another
supported language, recognition follows it. The voice speaks each line in the
language of its script.
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

# Study session that starts with a topic picked in the app
TOPIC_GREETINGS = {
    "ml-IN": "ഹായ്! ഇന്ന് നമുക്ക് {topic} പഠിക്കാം. ഞാൻ ലളിതമായി പറഞ്ഞു തുടങ്ങട്ടെ?",
    "te-IN": "హాయ్! ఈ రోజు మనం {topic} గురించి నేర్చుకుందాం. నేను సింపుల్ గా మొదలుపెట్టనా?",
    "en-IN": "Hey! Today let's study {topic} together. Shall I start with the simple version?",
}

# "Just talk" mode: the buddy as a listener
TALK_GREETINGS = {
    "ml-IN": "ഹായ്! ഞാൻ ഇവിടെ ഉണ്ട്. ഇന്ന് എങ്ങനെയുണ്ട്? എന്തും പറയാം, ഞാൻ കേൾക്കാം.",
    "te-IN": "హాయ్! నేను ఇక్కడే ఉన్నాను. ఈ రోజు ఎలా ఉంది? ఏదైనా చెప్పు, నేను వింటాను.",
    "en-IN": "Hey, I'm here. How's your day going? Tell me anything, I'm listening.",
}

# Short lines the agent says itself (agents/interview_monitor.py keys)
NUDGES = {
    "repeat_offer": {
        "ml-IN": "തിരക്കൊന്നുമില്ല! ഞാൻ ഒന്നുകൂടി പറയണോ, അതോ ഒരു ചെറിയ ക്ലൂ തരട്ടെ?",
        "te-IN": "తొందరేమీ లేదు! నేను మళ్ళీ చెప్పనా, లేక చిన్న హింట్ ఇవ్వనా?",
        "en-IN": "No rush! Want me to say that again, or shall I give you a little hint?",
    },
}


# Said when the learner switches with the language buttons
SWITCHED = {
    "ml-IN": "ശരി, ഇനി നമുക്ക് മലയാളത്തിൽ സംസാരിക്കാം!",
    "te-IN": "సరే, ఇప్పుడు తెలుగులో మాట్లాడుకుందాం!",
    "en-IN": "Sure, let's switch to English!",
}


def normalize(code: object | None) -> str | None:
    """A speech-recognition language ("te", "te-IN", "ml-in") as one of SUPPORTED."""
    if not code:
        return None
    prefix = str(code).strip().lower().split("-")[0]
    return next((lang for lang in SUPPORTED if lang.lower().startswith(prefix + "-")), None)


# All Indian scripts (Devanagari .. Malayalam), for text in one we don't speak
_INDIC = range(0x0900, 0x0D80)


def language_of(text: str, default: str = "en-IN") -> str:
    """The language to speak `text` in, from its script.

    Telugu/Malayalam script -> that language; Latin-only -> English; another
    Indian script (e.g. Kannada from a misheard turn) or no letters -> `default`
    (the current language), never the English voice.
    """
    counts = {lang: sum(1 for ch in text if ord(ch) in block) for lang, block in _SCRIPTS.items()}
    lang, n = max(counts.items(), key=lambda kv: kv[1])
    if n:
        return lang
    if any(ord(ch) in _INDIC for ch in text):
        return default
    return "en-IN" if any(ch.isalpha() for ch in text) else default


def greeting(language: str | None, mode: str | None = None, topic: str | None = None) -> str:
    if mode != "talk" and topic:
        return TOPIC_GREETINGS.get(language or "", TOPIC_GREETINGS["ml-IN"]).format(topic=topic)
    lines = TALK_GREETINGS if mode == "talk" else GREETINGS
    return lines.get(language or "", lines["ml-IN"])


def nudge(key: str, language: str | None) -> str:
    lines = NUDGES.get(key, {})
    return lines.get(language or "", lines.get("en-IN", ""))
