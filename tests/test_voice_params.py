from shorts.openai_helpers import _speech_kwargs, voice_params_hash


def test_speech_kwargs_omits_unset_knobs():
    kwargs = _speech_kwargs(text="hi", model="gpt-4o-mini-tts", voice="alloy")
    assert kwargs == {"model": "gpt-4o-mini-tts", "voice": "alloy", "input": "hi"}


def test_speech_kwargs_includes_set_knobs():
    kwargs = _speech_kwargs(
        text="hi",
        model="gpt-4o-mini-tts",
        voice="alloy",
        instructions="calm narrator",
        speed=1.25,
    )
    assert kwargs["instructions"] == "calm narrator"
    assert kwargs["speed"] == 1.25


def test_speech_kwargs_blank_instructions_dropped():
    kwargs = _speech_kwargs(
        text="hi", model="m", voice="alloy", instructions="", speed=None
    )
    assert "instructions" not in kwargs
    assert "speed" not in kwargs


def test_speech_kwargs_speed_zero_is_kept():
    # 0.0 is falsy but a real value; only None means "unset"
    kwargs = _speech_kwargs(text="hi", model="m", voice="alloy", speed=0.0)
    assert kwargs["speed"] == 0.0


def _h(**over):
    base = dict(model="gpt-4o-mini-tts", voice="alloy", instructions=None, speed=None)
    base.update(over)
    return voice_params_hash(**base)


def test_voice_params_hash_stable():
    assert _h() == _h()


def test_voice_params_hash_changes_with_each_knob():
    baseline = _h()
    assert _h(model="tts-1") != baseline
    assert _h(voice="verse") != baseline
    assert _h(instructions="calm") != baseline
    assert _h(speed=1.5) != baseline


def test_voice_params_hash_speed_none_vs_one_differ():
    assert _h(speed=None) != _h(speed=1.0)
