import json

from brain.processor import _page
from brain.tools.fast.conversation import page_block


def test_page_parses_json_and_rejects_junk():
    page = {"topic": "Photosynthesis", "points": ["Leaves make food"], "page_text": "Plants use light."}
    assert _page(json.dumps(page))["topic"] == "Photosynthesis"
    assert _page(None) is None
    assert _page("not json") is None
    assert _page(json.dumps({"topic": "x", "points": []})) is None


def test_page_block_only_when_a_page_was_read():
    assert page_block({}) == ""
    block = page_block({"page_text": "Plants use light."})
    assert "<textbook_page>" in block and "Plants use light." in block
