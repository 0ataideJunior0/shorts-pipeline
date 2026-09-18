import json
import urllib.error

import pytest

from shorts.voicestudio_tts import (
    VoiceStudioError,
    _build_payload,
    synthesize_speech,
    voice_params_hash,
)


def _h(**over):
    base = dict(model="omnivoice", voice="39f10351", language=None, speed=1.0, instruct=None)
    base.update(over)
    return voice_params_hash(**base)


def test_voice_params_hash_stable():
    assert _h() == _h()


def test_voice_params_hash_changes_with_each_knob():
    baseline = _h()
    assert _h(model="voxcpm2") != baseline
    assert _h(voice="demo0001") != baseline
    assert _h(language="pt") != baseline
    assert _h(speed=1.25) != baseline
    assert _h(instruct="fale num tom calmo") != baseline


def test_build_payload_omits_unset_optional_fields():
    payload = _build_payload(
        text="ola mundo", model="omnivoice", voice="39f10351",
        language=None, speed=1.0, instruct=None,
    )
    assert payload == {
        "model": "omnivoice",
        "voice": "39f10351",
        "input": "ola mundo",
        "response_format": "mp3",
        "speed": 1.0,
    }


def test_build_payload_includes_optional_fields_when_set():
    payload = _build_payload(
        text="ola mundo", model="omnivoice", voice="39f10351",
        language="pt", speed=1.25, instruct="fale num tom calmo",
    )
    assert payload["language"] == "pt"
    assert payload["instruct"] == "fale num tom calmo"
    assert payload["speed"] == 1.25


def test_synthesize_speech_writes_response_bytes(tmp_path, monkeypatch):
    out_path = tmp_path / "out.mp3"
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return b"fake-mp3-bytes"

    def fake_urlopen(request, timeout=None):
        captured["url"] = request.full_url
        captured["method"] = request.get_method()
        captured["body"] = json.loads(request.data)
        captured["headers"] = dict(request.header_items())
        return FakeResponse()

    monkeypatch.setattr("shorts.voicestudio_tts.urllib.request.urlopen", fake_urlopen)

    synthesize_speech(
        base_url="http://localhost:3900",
        text="ola mundo",
        out_path=out_path,
        model="omnivoice",
        voice="39f10351",
    )

    assert out_path.read_bytes() == b"fake-mp3-bytes"
    assert captured["url"] == "http://localhost:3900/v1/audio/speech"
    assert captured["method"] == "POST"
    assert captured["body"]["input"] == "ola mundo"
    assert captured["headers"]["Content-type"] == "application/json"


def test_synthesize_speech_strips_trailing_slash_from_base_url(tmp_path, monkeypatch):
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return b"x"

    def fake_urlopen(request, timeout=None):
        captured["url"] = request.full_url
        return FakeResponse()

    monkeypatch.setattr("shorts.voicestudio_tts.urllib.request.urlopen", fake_urlopen)

    synthesize_speech(
        base_url="http://localhost:3900/",
        text="ola",
        out_path=tmp_path / "out.mp3",
        model="omnivoice",
        voice="39f10351",
    )

    assert captured["url"] == "http://localhost:3900/v1/audio/speech"


def test_synthesize_speech_raises_clear_error_when_server_unreachable(tmp_path, monkeypatch):
    def fake_urlopen(request, timeout=None):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr("shorts.voicestudio_tts.urllib.request.urlopen", fake_urlopen)

    with pytest.raises(VoiceStudioError, match="http://localhost:3900"):
        synthesize_speech(
            base_url="http://localhost:3900",
            text="ola",
            out_path=tmp_path / "out.mp3",
            model="omnivoice",
            voice="39f10351",
        )
