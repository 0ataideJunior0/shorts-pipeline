from __future__ import annotations

import hashlib
from pathlib import Path

from google import genai
from google.genai import types

from shorts.shell import run_cmd

_PCM_SAMPLE_RATE = 24000


def voice_params_hash(*, model: str, voice: str, instructions: str | None) -> str:
    """Stable digest of the TTS knobs that affect the produced audio.

    Folded into the voice/render staleness checks so editing `[voice]` in
    config.toml re-synthesizes on the next run without `--force`.
    """
    parts = [model, voice, instructions or ""]
    return hashlib.sha256("\n".join(parts).encode()).hexdigest()


def _build_contents(text: str, instructions: str | None) -> str:
    if instructions:
        return f"{instructions}: {text}"
    return text


def _pcm_to_mp3(pcm_bytes: bytes, out_path: Path) -> None:
    tmp_path = out_path.with_suffix(".pcm")
    tmp_path.write_bytes(pcm_bytes)
    try:
        run_cmd(
            [
                "ffmpeg", "-y",
                "-f", "s16le", "-ar", str(_PCM_SAMPLE_RATE), "-ac", "1",
                "-i", str(tmp_path),
                str(out_path),
            ]
        )
    finally:
        tmp_path.unlink(missing_ok=True)


def get_client(api_key: str) -> genai.Client:
    return genai.Client(api_key=api_key)


def synthesize_speech(
    client: genai.Client,
    *,
    text: str,
    out_path: Path,
    model: str,
    voice: str,
    instructions: str | None = None,
) -> None:
    response = client.models.generate_content(
        model=model,
        contents=_build_contents(text, instructions),
        config=types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice)
                )
            ),
        ),
    )
    pcm_bytes = response.candidates[0].content.parts[0].inline_data.data
    _pcm_to_mp3(pcm_bytes, out_path)
