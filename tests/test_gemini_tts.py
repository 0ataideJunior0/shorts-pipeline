import math
import struct

from shorts.gemini_tts import _build_contents, _pcm_to_mp3, voice_params_hash


def test_build_contents_without_instructions():
    assert _build_contents("hello world", None) == "hello world"


def test_build_contents_with_instructions_prefixes_style_prompt():
    result = _build_contents("hello world", "narrate calmly, pt-BR")
    assert result == "narrate calmly, pt-BR: hello world"


def test_build_contents_blank_instructions_treated_as_unset():
    assert _build_contents("hello world", "") == "hello world"


def _sine_pcm_s16le(*, seconds: float, sample_rate: int = 24000) -> bytes:
    n = int(seconds * sample_rate)
    samples = (
        int(3000 * math.sin(2 * math.pi * 440 * i / sample_rate)) for i in range(n)
    )
    return struct.pack(f"<{n}h", *samples)


def test_pcm_to_mp3_writes_playable_audio_of_expected_duration(tmp_path):
    from shorts.shell import ffprobe_duration

    pcm_bytes = _sine_pcm_s16le(seconds=1.0)
    out_path = tmp_path / "out.mp3"

    _pcm_to_mp3(pcm_bytes, out_path)

    assert out_path.exists()
    assert math.isclose(ffprobe_duration(out_path), 1.0, abs_tol=0.1)


def test_pcm_to_mp3_cleans_up_temp_pcm_file(tmp_path):
    out_path = tmp_path / "out.mp3"

    _pcm_to_mp3(_sine_pcm_s16le(seconds=0.1), out_path)

    assert not out_path.with_suffix(".pcm").exists()


def _h(**over):
    base = dict(model="gemini-2.5-pro-preview-tts", voice="Kore", instructions=None)
    base.update(over)
    return voice_params_hash(**base)


def test_voice_params_hash_stable():
    assert _h() == _h()


def test_voice_params_hash_changes_with_each_knob():
    baseline = _h()
    assert _h(model="gemini-2.5-flash-preview-tts") != baseline
    assert _h(voice="Puck") != baseline
    assert _h(instructions="calm, confident pace") != baseline
