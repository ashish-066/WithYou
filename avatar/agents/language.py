"""Which language the buddy speaks: Malayalam, Telugu, Tamil, Hindi or English.

Speech recognition is locked to the session's language (Sarvam's "auto" mode
heard Telugu as Kannada on a real mic). The learner switches with the language
buttons in the room, or by asking the buddy: when a reply comes in another
supported language, recognition follows it. The voice speaks each line in the
language of its script.
"""

from __future__ import annotations

SUPPORTED = ("ml-IN", "te-IN", "ta-IN", "hi-IN", "en-IN")

# Unicode blocks of the scripts we speak
_SCRIPTS = {
    "te-IN": range(0x0C00, 0x0C80),  # Telugu
    "ml-IN": range(0x0D00, 0x0D80),  # Malayalam
    "ta-IN": range(0x0B80, 0x0C00),  # Tamil
    "hi-IN": range(0x0900, 0x0980),  # Devanagari (Hindi)
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
    "ta-IN": (
        "ஹாய்! நான் உன் படிப்பு நண்பன். இன்னைக்கு என்ன படிக்கலாம்? "
        "ஏதாவது டாபிக் சொல்லு, இல்லனா சும்மா ஹாய் சொன்னா கூட போதும்."
    ),
    "hi-IN": (
        "हाय! मैं तुम्हारा स्टडी बडी हूँ। आज क्या पढ़ें? "
        "कोई भी टॉपिक बताओ, या बस हाय बोल दो, साथ में देख लेंगे।"
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
    "ta-IN": "ஹாய்! இன்னைக்கு நாம {topic} பத்தி படிக்கலாம். நான் சிம்பிளா ஆரம்பிக்கட்டுமா?",
    "hi-IN": "हाय! आज हम साथ में {topic} पढ़ेंगे। मैं आसान तरीके से शुरू करूँ?",
    "en-IN": "Hey! Today let's study {topic} together. Shall I start with the simple version?",
}

# "Just talk" mode: the buddy as a listener
TALK_GREETINGS = {
    "ml-IN": "ഹായ്! ഞാൻ ഇവിടെ ഉണ്ട്. ഇന്ന് എങ്ങനെയുണ്ട്? എന്തും പറയാം, ഞാൻ കേൾക്കാം.",
    "te-IN": "హాయ్! నేను ఇక్కడే ఉన్నాను. ఈ రోజు ఎలా ఉంది? ఏదైనా చెప్పు, నేను వింటాను.",
    "ta-IN": "ஹாய்! நான் இங்க தான் இருக்கேன். இன்னைக்கு எப்படி போச்சு? எதுவானாலும் சொல்லு, நான் கேக்கறேன்.",
    "hi-IN": "हाय! मैं यहीं हूँ। आज का दिन कैसा रहा? कुछ भी बताओ, मैं सुन रहा हूँ।",
    "en-IN": "Hey, I'm here. How's your day going? Tell me anything, I'm listening.",
}

# "Just talk" started from a mood chip on Home ("Stressed", "ఎగ్జామ్ భయం", ...)
TALK_MOOD_GREETINGS = {
    "ml-IN": "ഹായ്, ഞാൻ ഇവിടെ ഉണ്ട്. '{topic}' എന്നാണല്ലോ തോന്നുന്നത്. എന്താ പറ്റിയത്? പറയാൻ തോന്നുന്നതൊക്കെ പറഞ്ഞോ.",
    "te-IN": "హాయ్, నేను ఇక్కడే ఉన్నాను. '{topic}' అని అనిపిస్తోంది కదా. ఏం జరిగింది? నీకు చెప్పాలనిపించింది ఏదైనా చెప్పు.",
    "ta-IN": "ஹாய், நான் இங்க தான் இருக்கேன். '{topic}'னு தோணுதுன்னு சொன்ன. என்ன ஆச்சு? சொல்லணும்னு தோணுறதெல்லாம் சொல்லு.",
    "hi-IN": "हाय, मैं यहीं हूँ। तुमने कहा '{topic}' लग रहा है। क्या हुआ? आराम से बताओ, जो भी मन में है।",
    "en-IN": "Hey, I'm here. You said you're feeling '{topic}'. Want to tell me what's going on? Take your time.",
}

# Short lines the agent says itself (agents/interview_monitor.py keys)
NUDGES = {
    "repeat_offer": {
        "ml-IN": "തിരക്കൊന്നുമില്ല! ഞാൻ ഒന്നുകൂടി പറയണോ, അതോ ഒരു ചെറിയ ക്ലൂ തരട്ടെ?",
        "te-IN": "తొందరేమీ లేదు! నేను మళ్ళీ చెప్పనా, లేక చిన్న హింట్ ఇవ్వనా?",
        "ta-IN": "அவசரம் இல்ல! நான் திரும்ப சொல்லட்டுமா, இல்ல ஒரு சின்ன க்ளூ தரட்டுமா?",
        "hi-IN": "कोई जल्दी नहीं! मैं फिर से बोलूँ, या एक छोटा सा हिंट दूँ?",
        "en-IN": "No rush! Want me to say that again, or shall I give you a little hint?",
    },
}


# Said when the learner switches with the language buttons
SWITCHED = {
    "ml-IN": "ശരി, ഇനി നമുക്ക് മലയാളത്തിൽ സംസാരിക്കാം!",
    "te-IN": "సరే, ఇప్పుడు తెలుగులో మాట్లాడుకుందాం!",
    "ta-IN": "சரி, இனிமே தமிழ்ல பேசலாம்!",
    "hi-IN": "ठीक है, अब हिंदी में बात करते हैं!",
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

    Telugu/Malayalam/Tamil/Devanagari script -> that language; Latin-only -> English; another
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


TEACH_GREETINGS = {
    "ml-IN": "ഹായ്! ഇന്ന് നീയാണ് ടീച്ചർ. എനിക്ക് {topic} ഒട്ടും അറിയില്ല. എനിക്ക് ഒന്ന് പറഞ്ഞു തരാമോ?",
    "te-IN": "హాయ్! ఈ రోజు నువ్వే టీచర్. నాకు {topic} అస్సలు తెలీదు. నాకు కొంచెం చెప్తావా?",
    "ta-IN": "ஹாய்! இன்னைக்கு நீ தான் டீச்சர். எனக்கு {topic} பத்தி ஒண்ணுமே தெரியாது. கொஞ்சம் சொல்லித் தருவியா?",
    "hi-IN": "हाय! आज तुम टीचर हो। मुझे {topic} के बारे में कुछ नहीं पता। मुझे समझाओगे?",
    "en-IN": "Hey! Today you're the teacher. I don't know anything about {topic}. Can you explain it to me?",
}
TEACH_GREETINGS_NO_TOPIC = {
    "ml-IN": "ഹായ്! ഇന്ന് നീയാണ് ടീച്ചർ. ഏത് ടോപിക് ആണ് എന്നെ പഠിപ്പിക്കുന്നത്?",
    "te-IN": "హాయ్! ఈ రోజు నువ్వే టీచర్. నాకు ఏ టాపిక్ నేర్పిస్తావు?",
    "ta-IN": "ஹாய்! இன்னைக்கு நீ தான் டீச்சர். எனக்கு எந்த டாபிக் சொல்லித் தரப்போற?",
    "hi-IN": "हाय! आज तुम टीचर हो। मुझे कौन सा टॉपिक सिखाओगे?",
    "en-IN": "Hey! Today you're the teacher. Which topic will you teach me?",
}


def greeting(language: str | None, mode: str | None = None, topic: str | None = None, style: str | None = None) -> str:
    if mode != "talk" and style == "teach":
        if topic:
            return TEACH_GREETINGS.get(language or "", TEACH_GREETINGS["ml-IN"]).format(topic=topic)
        return TEACH_GREETINGS_NO_TOPIC.get(language or "", TEACH_GREETINGS_NO_TOPIC["ml-IN"])
    if topic:
        lines = TALK_MOOD_GREETINGS if mode == "talk" else TOPIC_GREETINGS
        return lines.get(language or "", lines["ml-IN"]).format(topic=topic)
    lines = TALK_GREETINGS if mode == "talk" else GREETINGS
    return lines.get(language or "", lines["ml-IN"])


def nudge(key: str, language: str | None) -> str:
    lines = NUDGES.get(key, {})
    return lines.get(language or "", lines.get("en-IN", ""))
