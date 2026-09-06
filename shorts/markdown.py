from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class IdeaSpec:
    slug: str
    title: str
    hook: str
    narration_script: str
    asset_categories: list[str]
    source_start: str
    source_end: str
    est_duration_sec: int


def prefixed_slug(index: int, slug: str) -> str:
    return f"{index:02d}-{slug}"


def render_idea(idea: IdeaSpec, index: int) -> str:
    categories = ", ".join(idea.asset_categories)
    return (
        "---\n"
        f"slug: {prefixed_slug(index, idea.slug)}\n"
        f"title: {idea.title}\n"
        f'source_range: "{idea.source_start}-{idea.source_end}"\n'
        f"est_duration_sec: {idea.est_duration_sec}\n"
        f"asset_categories: [{categories}]\n"
        "---\n\n"
        "- [ ] Approved\n\n"
        "## Hook\n\n"
        f"{idea.hook.strip()}\n\n"
        "## Narration\n\n"
        f"{idea.narration_script.strip()}\n\n"
        "## Notes\n\n"
        f"Suggested asset categories: {categories}\n"
    )


@dataclass
class ParsedIdea:
    slug: str
    approved: bool
    narration: str
    frontmatter: dict


_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)
_APPROVED_RE = re.compile(r"^\s*-\s*\[([ xX])\]\s*Approved\s*$", re.MULTILINE)


def _parse_frontmatter(text: str) -> dict:
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return {}
    out: dict = {}
    for line in match.group(1).splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            out[key.strip()] = value.strip().strip('"')
    return out


def _section(text: str, name: str) -> str:
    pattern = re.compile(
        rf"^##\s+{re.escape(name)}\s*$(.*?)(?=^##\s+|\Z)",
        re.DOTALL | re.MULTILINE,
    )
    match = pattern.search(text)
    return match.group(1).strip() if match else ""


def parse_idea_file(text: str) -> ParsedIdea:
    frontmatter = _parse_frontmatter(text)
    approved_match = _APPROVED_RE.search(text)
    approved = bool(approved_match and approved_match.group(1).lower() == "x")
    return ParsedIdea(
        slug=frontmatter.get("slug", ""),
        approved=approved,
        narration=_section(text, "Narration"),
        frontmatter=frontmatter,
    )
