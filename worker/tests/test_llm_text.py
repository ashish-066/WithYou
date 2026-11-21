"""message_text: model replies as strings or content blocks."""

from types import SimpleNamespace

from langchain_core.messages import AIMessage

from core.llm_text import message_text


def test_string_content():
    assert message_text(AIMessage(content='{"ok": true}')) == '{"ok": true}'


def test_gemini_content_blocks():
    # Shape returned by current Gemini models through langchain-google-genai
    reply = AIMessage(content=[
        {"type": "text", "text": '{"ok": ', "extras": {"signature": "abc"}},
        {"type": "text", "text": "true}"},
    ])
    assert message_text(reply) == '{"ok": true}'


def test_non_text_blocks_are_skipped():
    reply = AIMessage(content=[
        {"type": "thinking", "thinking": "let me think"},
        "Hello",
        {"type": "text", "text": " world"},
    ])
    assert message_text(reply) == "Hello world"


def test_plain_strings_and_objects():
    assert message_text("already text") == "already text"
    assert message_text(SimpleNamespace(content="from a fake")) == "from a fake"
    assert message_text(SimpleNamespace(content=None)) == ""
