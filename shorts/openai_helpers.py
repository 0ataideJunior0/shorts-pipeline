from __future__ import annotations

import hashlib
import json
from pathlib import Path

from openai import OpenAI

from shorts.markdown import IdeaSpec
from shorts.transcript import Segment


def voice_params_hash(
    *, model: str, voice: str, instructions: str | None, speed: float | None
) -> str:
    """Stable digest of the TTS knobs that affect the produced audio.

    Folded into the voice/render staleness checks so editing `[voice]` in
    config.toml re-synthesizes on the next run without `--force`.
    """
    parts = [
        model,
        voice,
        instructions or "",
        "" if speed is None else format(float(speed), ".4f"),
    ]
    return hashlib.sha256("\n".join(parts).encode()).hexdigest()


def get_client(api_key: str) -> OpenAI:
    return OpenAI(api_key=api_key)


def transcribe_audio(client: OpenAI, path: Path, model: str) -> list[Segment]:
    with open(path, "rb") as fh:
        resp = client.audio.transcriptions.create(
            model=model,
            file=fh,
            response_format="verbose_json",
        )
    raw_segments = getattr(resp, "segments", None) or []
    out: list[Segment] = []
    for seg in raw_segments:
        if isinstance(seg, dict):
            out.append(Segment(float(seg["start"]), float(seg["end"]), seg["text"]))
        else:
            out.append(Segment(float(seg.start), float(seg.end), seg.text))
    return out


_IDEAS_SCHEMA = {
    "type": "object",
    "properties": {
        "ideas": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "slug": {"type": "string"},
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "tags": {"type": "array", "items": {"type": "string"}},
                    "hook": {"type": "string"},
                    "narration_script": {"type": "string"},
                    "asset_categories": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "source_start": {"type": "string"},
                    "source_end": {"type": "string"},
                    "est_duration_sec": {"type": "integer"},
                },
                "required": [
                    "slug", "title", "description", "tags", "hook", "narration_script",
                    "asset_categories", "source_start", "source_end",
                    "est_duration_sec",
                ],
                "additionalProperties": False,
            },
        }
    },
    "required": ["ideas"],
    "additionalProperties": False,
}

_STRUCTURAL_SUFFIX = (
    "\n\n---\n"
    "Return JSON that matches the provided schema exactly. source_start and "
    'source_end are timestamps like "12:30" locating the material in the source '
    "video. slug is 2-4 lowercase words joined by hyphens, with no numeric "
    "prefix. title is the short's headline. description is a 1-3 sentence "
    "publish caption for the short, written for the viewer, in the same "
    "language as the narration. tags is a short list (5-12) of YouTube upload "
    "tags for the short: plain keywords or short phrases, no '#', in the "
    "narration's language."
)


def generate_ideas(
    client: OpenAI,
    *,
    transcript_text: str,
    video_title: str,
    prompt: str,
    model: str,
    count: int,
) -> list[IdeaSpec]:
    system_prompt = prompt.strip() + _STRUCTURAL_SUFFIX
    user_prompt = (
        f"Source video title: {video_title}\n\n"
        f"Produce exactly {count} shorts ideas as JSON.\n\n"
        f"Transcript:\n{transcript_text}"
    )
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "shorts_ideas",
                "strict": True,
                "schema": _IDEAS_SCHEMA,
            },
        },
    )
    payload = json.loads(resp.choices[0].message.content)
    out: list[IdeaSpec] = []
    for item in payload["ideas"]:
        out.append(
            IdeaSpec(
                slug=item["slug"],
                title=item["title"],
                description=item["description"],
                tags=list(item["tags"]),
                hook=item["hook"],
                narration_script=item["narration_script"],
                asset_categories=list(item["asset_categories"]),
                source_start=item["source_start"],
                source_end=item["source_end"],
                est_duration_sec=int(item["est_duration_sec"]),
            )
        )
    return out


def _speech_kwargs(
    *,
    text: str,
    model: str,
    voice: str,
    instructions: str | None = None,
    speed: float | None = None,
) -> dict:
    """Build the audio.speech.create kwargs, omitting unset optional knobs.

    `instructions` (tone/style/pacing, gpt-4o-mini-tts) and `speed` (tts-1
    family) are only sent when configured, so leaving them unset keeps the
    request identical to the previous behaviour.
    """
    kwargs: dict = {"model": model, "voice": voice, "input": text}
    if instructions:
        kwargs["instructions"] = instructions
    if speed is not None:
        kwargs["speed"] = speed
    return kwargs


def synthesize_speech(
    client: OpenAI,
    *,
    text: str,
    out_path: Path,
    model: str,
    voice: str,
    instructions: str | None = None,
    speed: float | None = None,
) -> None:
    kwargs = _speech_kwargs(
        text=text,
        model=model,
        voice=voice,
        instructions=instructions,
        speed=speed,
    )
    with client.audio.speech.with_streaming_response.create(**kwargs) as response:
        response.stream_to_file(out_path)
