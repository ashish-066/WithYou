"""Saved text shown in the learner's language (services/translate.py)."""

from services import translate as tr


def test_only_text_in_another_script_is_translated():
    assert not tr.needs_translation("ఈ రోజు బాగా చేశావు", "te-IN")
    assert tr.needs_translation("ഇന്ന് നന്നായി ചെയ്തു", "te-IN")
    assert tr.needs_translation("Photosynthesis", "te-IN")
    assert not tr.needs_translation("Photosynthesis", "en-IN")
    assert not tr.needs_translation("", "te-IN") and not tr.needs_translation(None, "te-IN")


async def test_failure_shows_the_original_and_success_is_cached(redis, monkeypatch):
    import core.redis as core_redis
    from core.config import settings

    monkeypatch.setattr(settings, "redis_url", "redis://localhost:6379/15")
    monkeypatch.setattr(core_redis, "_pool", None)
    monkeypatch.setattr(settings, "sarvam_api_key", "k")
    calls = []

    class Resp:
        def __init__(self, ok):
            self.ok = ok

        def raise_for_status(self):
            if not self.ok:
                raise RuntimeError("down")

        def json(self):
            return {"translated_text": "నీటి చక్రం"}

    class Client:
        ok = False

        def __init__(self, timeout):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, headers, json):
            calls.append(json)
            return Resp(Client.ok)

    monkeypatch.setattr(tr.httpx, "AsyncClient", Client)
    assert await tr.translate("ജലചക്രം", "te-IN") == "ജലചക്രം"  # down: original
    Client.ok = True
    assert await tr.translate("ജലചക്രം", "te-IN") == "నీటి చక్రం"
    assert calls[-1]["source_language_code"] == "ml-IN" and calls[-1]["model"] == "sarvam-translate:v1"
    n = len(calls)
    assert await tr.translate("ജലചക്രം", "te-IN") == "నీటి చక్రం" and len(calls) == n  # cached
    if core_redis._pool is not None:
        await core_redis._pool.aclose()
    monkeypatch.setattr(core_redis, "_pool", None)


def test_looks_broken_catches_model_chatter():
    from services.translate import looks_broken

    assert looks_broken("ప్రకాశసంశ్లేషణ", "The translation of the input text is: Photosynthesis")
    assert looks_broken("నీటి చక్రం", "x" * 200)
    assert not looks_broken("నీటి చక్రం", "Water cycle")
