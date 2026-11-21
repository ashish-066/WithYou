import base64

import pytest
from fastapi import HTTPException

from api.page_routes import _decode, _parse


def test_decode_accepts_images_only():
    url = "data:image/jpeg;base64," + base64.b64encode(b"abc").decode()
    assert _decode(url) == ("image/jpeg", b"abc")
    with pytest.raises(HTTPException):
        _decode("data:text/html;base64,PGI+")
    with pytest.raises(HTTPException):
        _decode("data:image/png;base64,***")


def test_parse_finds_json():
    assert _parse('```json\n{"topic": "Gravity"}\n```') == {"topic": "Gravity"}
    assert _parse("no json") == {}
