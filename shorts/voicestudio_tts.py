from __future__ import annotations

import hashlib
import json
import urllib.error
import urllib.request
from pathlib import Path


class VoiceStudioError(Exception):
    pass


def voice_params_hash(
    *, model: str, voice: str, language: str | None, speed: float, instruct: str | None
) -> str:
    """Stable digest of the TTS knobs that affect the produced audio.

    Folded into the voice/render staleness checks so editing `[voice]` in
    config.toml re-synthesizes on the next run without `--force`.
    """
    parts = [model, voice, language or "", str(speed), instruct or ""]
    return hashlib.sha256("\n".join(parts).encode()).hexdigest()


def _build_payload(
    *,
    text: str,
    model: str,
    voice: str,
    language: str | None,
    speed: float,
    instruct: str | None,
) -> dict:
    payload: dict = {
        "model": model,
        "voice": voice,
        "input": text,
        "response_format": "mp3",
        "speed": speed,
    }
    if language:
        payload["language"] = language
    if instruct:
        payload["instruct"] = instruct
    return payload


def synthesize_speech(
    *,
    base_url: str,
    text: str,
    out_path: Path,
    model: str,
    voice: str,
    language: str | None = None,
    speed: float = 1.0,
    instruct: str | None = None,
) -> None:
    payload = _build_payload(
        text=text, model=model, voice=voice, language=language, speed=speed, instruct=instruct
    )
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/v1/audio/speech",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            audio_bytes = response.read()
    except urllib.error.URLError as exc:
        raise VoiceStudioError(
            f"VoiceStudio nao esta acessivel em {base_url} "
            f"- abra o app antes de rodar 'voice' ({exc})"
        ) from exc
    out_path.write_bytes(audio_bytes)
