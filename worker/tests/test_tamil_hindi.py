"""Tamil and Hindi: language switching, goodbyes, crisis detection, recap text."""

from brain import interview_flow, talk
from brain.language_switch import requested_language
from brain.tools.slow.report_generator import FALLBACK, HELPLINE
from brain.tools.fast.conversation import LANGUAGE_RULES


def test_switch_requests():
    assert requested_language("தமிழ்ல சொல்லு", "te-IN") == "ta-IN"
    assert requested_language("हिंदी में बोलो", "ta-IN") == "hi-IN"
    assert requested_language("speak hindi please", "en-IN") == "hi-IN"
    assert requested_language("switch to tamil", "ml-IN") == "ta-IN"
    assert requested_language("इंग्लिश में बताओ", "hi-IN") == "en-IN"


def test_goodbyes_and_confirmations():
    assert interview_flow.wants_to_stop("சரி பை")
    assert interview_flow.wants_to_stop("आज के लिए इतना ही, बाय")
    assert not interview_flow.wants_to_stop("அந்த பையன் படிக்கிறான்")  # "boy", not "bye"
    assert interview_flow.closing_message("completed", "ta-IN") != interview_flow.closing_message("completed", "en-IN")
    assert "बाय" in interview_flow.closing_message("completed", "hi-IN")


def test_crisis_detection():
    assert talk.in_crisis("எனக்கு சாகணும் போல இருக்கு")
    assert talk.in_crisis("मुझे मरना चाहता हूँ लगता है")
    assert talk.in_crisis("mujhe jeena nahi chahta")
    assert not talk.in_crisis("आज परीक्षा बहुत कठिन थी")


def test_every_language_has_text():
    for lang in ("ta-IN", "hi-IN"):
        assert lang in LANGUAGE_RULES and lang in HELPLINE and lang in FALLBACK
        assert lang in talk.TALK_GOODBYES
