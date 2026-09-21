from __future__ import annotations

import json
from pathlib import Path

from openai import OpenAI

from shorts.markdown import IdeaSpec
from shorts.transcript import Segment


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


_REFINE_SYSTEM_PROMPTS = {
    "title": (
        "You are an expert YouTube Shorts creator and copywriter. Refine and optimize the YouTube Short title.\n"
        "Produce a punchy, high-CTR YouTube Short title in the language of the narration.\n"
        "Rules:\n"
        "- Must be a single line.\n"
        "- No quotes.\n"
        "- No markdown formatting (no bold, no italics).\n"
        "- No prefixes like 'Title:' or explanations.\n"
        "- Return ONLY the refined title."
    ),
    "description": (
        "You are an expert YouTube Shorts creator and copywriter. Refine and optimize the YouTube Short description.\n"
        "Produce a 1-3 sentence engaging YouTube Short publish caption in the language of the narration.\n"
        "Rules:\n"
        "- 1-3 sentences.\n"
        "- No markdown fences or formatting.\n"
        "- No quotes.\n"
        "- No prefixes like 'Description:' or explanations.\n"
        "- Return ONLY the refined description."
    ),
    "tags": (
        "You are an expert YouTube Shorts creator and SEO specialist. Refine and optimize the YouTube Short upload tags.\n"
        "Produce 5-12 comma-separated YouTube upload tags/keywords in the language of the narration.\n"
        "Rules:\n"
        "- 5-12 comma-separated tags.\n"
        "- No '#' hashtags (plain keywords or short phrases only).\n"
        "- No quotes or markdown formatting.\n"
        "- No prefixes like 'Tags:' or explanations.\n"
        "- Return ONLY the comma-separated tags."
    ),
}


def _strip_wrappers(s: str) -> str:
    while True:
        prev = s
        s = s.strip()
        s = s.strip('\'"“”‘’`')
        if (s.startswith("**") and s.endswith("**")) or (
            s.startswith("__") and s.endswith("__")
        ):
            s = s[2:-2]
        if (s.startswith("*") and s.endswith("*")) or (
            s.startswith("_") and s.endswith("_")
        ):
            s = s[1:-1]
        s = s.strip()
        if s == prev:
            break
    return s


def _clean_refined_text(text: str, field: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```") and cleaned.endswith("```"):
        lines = cleaned.splitlines()
        if len(lines) >= 2:
            cleaned = "\n".join(lines[1:-1]).strip()
        else:
            cleaned = cleaned.strip("`").strip()

    if field == "title":
        lines = [line.strip() for line in cleaned.splitlines() if line.strip()]
        cleaned = lines[0] if lines else ""
        cleaned = _strip_wrappers(cleaned)
        if cleaned.lower().startswith("title:"):
            cleaned = cleaned[6:].strip()
        cleaned = _strip_wrappers(cleaned)
    elif field == "description":
        cleaned = _strip_wrappers(cleaned)
        if cleaned.lower().startswith("description:"):
            cleaned = cleaned[12:].strip()
        cleaned = _strip_wrappers(cleaned)
    elif field == "tags":
        cleaned = _strip_wrappers(cleaned)
        if cleaned.lower().startswith("tags:"):
            cleaned = cleaned[5:].strip()
        cleaned = _strip_wrappers(cleaned)
        tags_list = [
            _strip_wrappers(t.strip().lstrip("#").strip())
            for t in cleaned.split(",")
            if t.strip()
        ]
        cleaned = ", ".join(t for t in tags_list if t)
    else:
        cleaned = _strip_wrappers(cleaned)

    return cleaned


def refine_idea_text(
    client: OpenAI,
    *,
    field: str,
    user_prompt: str = "",
    current_title: str = "",
    current_description: str = "",
    current_tags: str = "",
    narration: str = "",
    hook: str = "",
    video_title: str = "",
    model: str,
) -> str:
    if field not in ("title", "description", "tags"):
        raise ValueError(f"invalid field: {field}")

    system_prompt = _REFINE_SYSTEM_PROMPTS[field]

    context_lines: list[str] = []
    if video_title:
        context_lines.append(f"Source video title: {video_title}")
    if hook:
        context_lines.append(f"Hook: {hook}")
    if narration:
        context_lines.append(f"Narration: {narration}")
    if current_title:
        context_lines.append(f"Current title: {current_title}")
    if current_description:
        context_lines.append(f"Current description: {current_description}")
    if current_tags:
        context_lines.append(f"Current tags: {current_tags}")
    if user_prompt:
        context_lines.append(f"User instruction: {user_prompt.strip()}")

    user_prompt_content = "\n".join(context_lines)
    if user_prompt_content:
        user_prompt_content += f"\n\nRefine the {field}."
    else:
        user_prompt_content = f"Refine the {field}."

    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt_content},
        ],
    )
    raw_text = resp.choices[0].message.content or ""
    return _clean_refined_text(raw_text, field)

