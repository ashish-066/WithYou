"""Desktop app proctoring events are accepted and count towards the score."""

import pytest
from pydantic import ValidationError

from api.proctoring_routes import FLAG_DESCRIPTIONS, _calculate_integrity_score
from api.proctoring_schemas import CheatFlagRequest

DESKTOP_FLAGS = [
    "blocked_app",
    "second_screen",
    "app_closed",
    "exit_attempt",
    "emergency_exit",
    "lock_expired",
    "browser_mode",
]


@pytest.mark.parametrize("flag_type", DESKTOP_FLAGS)
def test_desktop_flags_are_accepted_and_described(flag_type):
    flag = CheatFlagRequest(
        session_id="s1", flag_type=flag_type, severity="high", confidence=1, description="x"
    )
    assert flag.flag_type == flag_type
    assert flag_type in FLAG_DESCRIPTIONS


def test_unknown_flag_is_rejected():
    with pytest.raises(ValidationError):
        CheatFlagRequest(
            session_id="s1", flag_type="made_up", severity="high", confidence=1, description="x"
        )


def test_closing_the_app_costs_more_than_an_accidental_attempt():
    def score(flag_type):
        return _calculate_integrity_score(
            [{"flag_type": flag_type, "severity": "medium", "confidence": 1.0}]
        )

    assert score("app_closed") < score("exit_attempt") < 1.0
