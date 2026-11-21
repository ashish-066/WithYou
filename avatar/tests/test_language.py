"""Phase 2: the voice follows the learner's language (Malayalam / Telugu / English)."""

from agents import language as lang
from agents.entrypoint import BuddyVoice, TurnRelay
from services.streams import AvatarStreamManager

REQUESTS = "test:requests"


def test_language_of_a_reply_follows_its_script():
    assert lang.language_of("ప్రకాశసంశ్లేషణ అంటే మొక్కలు ఆహారం తయారు చేసుకోవడం") == "te-IN"
    assert lang.language_of("ഇലകൾക്ക് പച്ച നിറം കൊടുക്കുന്നത് chlorophyll ആണ്") == "ml-IN"
    assert lang.language_of("Plants make food from sunlight.") == "en-IN"
    # Mostly Telugu with an English term stays Telugu
    assert lang.language_of("chlorophyll అనే ఆకుపచ్చ రంగు") == "te-IN"
    assert lang.language_of("...", default="ml-IN") == "ml-IN"  # no letters: keep current
    # Another Indian script (Telugu speech misheard as Kannada): current voice, never English
    assert lang.language_of("ನ್ಯೂರೋ ಸರ್ವ ಡೆವಲಪ್ಮೆಂಟ್", default="te-IN") == "te-IN"


def test_speech_recognition_codes_are_normalised():
    assert lang.normalize("te-IN") == "te-IN"
    assert lang.normalize("ml") == "ml-IN"
    assert lang.normalize("EN-in") == "en-IN"
    assert lang.normalize("fr-FR") is None and lang.normalize(None) is None


def test_greeting_and_nudges_in_each_language():
    assert lang.language_of(lang.greeting("te-IN")) == "te-IN"
    assert lang.language_of(lang.greeting("ml-IN")) == "ml-IN"
    assert lang.language_of(lang.greeting(None)) == "ml-IN"  # default
    assert lang.greeting("te-IN", "talk") == lang.TALK_GREETINGS["te-IN"]
    assert "Gravity" in lang.greeting("te-IN", "study", "Gravity")
    assert "స్ట్రెస్" in lang.greeting("te-IN", "talk", "స్ట్రెస్ గా ఉంది")  # talk acknowledges the mood
    assert lang.language_of(lang.greeting("ml-IN", "talk")) == "ml-IN"
    for code in lang.SUPPORTED:
        assert lang.language_of(lang.nudge("repeat_offer", code)) == code


async def test_turns_carry_the_spoken_language(redis):
    relay = TurnRelay("A", AvatarStreamManager(redis, request_stream=REQUESTS))
    await relay.send("hello")
    relay.language = "te-IN"
    await relay.send("నమస్కారం")
    entries = [d for _, d in await redis.xrange(REQUESTS)]
    assert "language" not in entries[0]
    assert entries[1]["language"] == "te-IN"


from livekit.plugins import sarvam  # noqa: E402


class FakeSarvamTTS(sarvam.TTS):
    def __init__(self):  # no network, no API key
        self.updates = []

    def update_options(self, **kw):
        self.updates.append(kw["target_language_code"])


class FakeSarvamSTT(sarvam.STTRealtime):
    def __init__(self):
        self.updates = []

    def update_options(self, **kw):
        self.updates.append(kw["language"])


def test_voice_switches_language_before_a_line():
    tts = FakeSarvamTTS()
    voice = BuddyVoice(tts, "ml-IN")
    voice.prepare("ഹായ്! ഇന്ന് നമുക്ക് എന്ത് പഠിക്കാം?")  # same language: no change
    voice.prepare("సరే, తెలుగులో చెప్తాను")
    voice.prepare("Okay, English it is!")
    assert tts.updates == ["te-IN", "en-IN"] and voice.language == "en-IN"


class _Relay:
    language = "te-IN"


def test_recognition_follows_the_buddy_into_another_indian_language():
    tts, stt, relay = FakeSarvamTTS(), FakeSarvamSTT(), _Relay()
    voice = BuddyVoice(tts, "te-IN", stt=stt, relay=relay)
    voice.prepare("Sure, a quick English word: photosynthesis.")  # English: listening stays Telugu
    assert stt.updates == [] and relay.language == "te-IN"
    voice.prepare("ശരി, ഇനി മലയാളത്തിൽ പറയാം.")  # learner asked for Malayalam
    assert stt.updates == ["ml-IN"] and relay.language == "ml-IN"


def test_language_buttons_switch_listening_and_voice():
    tts, stt, relay = FakeSarvamTTS(), FakeSarvamSTT(), _Relay()
    voice = BuddyVoice(tts, "te-IN", stt=stt, relay=relay)
    voice.switch_to("en-IN")
    assert (stt.updates, tts.updates, relay.language, voice.language) == (
        ["en-IN"], ["en-IN"], "en-IN", "en-IN"
    )
    assert lang.language_of(lang.SWITCHED["ml-IN"]) == "ml-IN"
    assert lang.language_of(lang.SWITCHED["te-IN"]) == "te-IN"


def test_teach_greeting():
    from agents.language import greeting

    assert "teacher" in greeting("en-IN", "study", "Gravity", "teach")
    assert "Gravity" in greeting("en-IN", "study", "Gravity", "teach")
    assert "teacher" not in greeting("en-IN", "study", "Gravity")
    assert "teacher" not in greeting("en-IN", "talk", "tired", "teach")
