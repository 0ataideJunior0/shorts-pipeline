from __future__ import annotations

import json

from shorts.markdown import replace_section, set_approved, set_frontmatter_value


class EditError(Exception):
    """An edit request the server refuses; the message is shown to the user."""


def apply_idea_edit(
    md_text: str,
    *,
    title: str,
    description: str,
    tags: str,
    narration: str,
    approved: bool,
) -> str:
    try:
        out = set_frontmatter_value(md_text, "title", title)
        out = replace_section(out, "Description", description)
        out = replace_section(out, "Tags", tags)
        out = replace_section(out, "Narration", narration)
        return set_approved(out, approved)
    except ValueError as exc:
        raise EditError(f"unexpected idea file format: {exc}") from exc


def build_prompt_json(prompt: str) -> str:
    if not prompt.strip():
        raise EditError("prompt must not be empty")
    return json.dumps({"prompt": prompt}, indent=2, ensure_ascii=False) + "\n"


def validate_plan_text(text: str) -> str:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise EditError(f"plan is not valid JSON: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("beats"), list):
        raise EditError('plan must be a JSON object with a "beats" array')
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"
