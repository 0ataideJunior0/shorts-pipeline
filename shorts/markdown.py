from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class IdeaSpec:
    slug: str
    title: str
    description: str
    tags: list[str]
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
        "## Description\n\n"
        f"{idea.description.strip()}\n\n"
        "## Tags\n\n"
        f"{', '.join(t.strip() for t in idea.tags if t.strip())}\n\n"
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
    description: str
    tags: str
    frontmatter: dict


_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)
# [ \t] rather than \s so a substitution can't swallow the blank lines around it
_APPROVED_RE = re.compile(r"^[ \t]*-[ \t]*\[([ xX])\][ \t]*Approved[ \t]*$", re.MULTILINE)


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
        description=_section(text, "Description"),
        tags=_section(text, "Tags"),
        frontmatter=frontmatter,
    )


def replace_section(text: str, name: str, new_body: str) -> str:
    """Replace the body under ``## <name>`` with ``new_body`` (stripped)."""
    pattern = re.compile(
        rf"(^##\s+{re.escape(name)}\s*$\n\n)(.*?)(?=^##\s+|\Z)",
        re.DOTALL | re.MULTILINE,
    )
    if not pattern.search(text):
        raise ValueError(f"no '## {name}' section")
    return pattern.sub(
        lambda m: m.group(1) + new_body.strip() + "\n\n", text
    )


def set_approved(text: str, approved: bool) -> str:
    """Set the ``- [ ] Approved`` / ``- [x] Approved`` checkbox."""
    box = "x" if approved else " "
    new_text, count = _APPROVED_RE.subn(f"- [{box}] Approved", text, count=1)
    if count == 0:
        raise ValueError("no '- [ ] Approved' line")
    return new_text


def set_frontmatter_value(text: str, key: str, value: str) -> str:
    """Replace ``key: ...`` inside the frontmatter block.

    ``value`` is flattened to a single line (whitespace collapsed). Raises
    ``ValueError`` if there is no frontmatter block or no such key in it.
    """
    match = _FRONTMATTER_RE.match(text)
    if not match:
        raise ValueError("no frontmatter block")
    block = match.group(1)
    line_re = re.compile(rf"^{re.escape(key)}:.*$", re.MULTILINE)
    if not line_re.search(block):
        raise ValueError(f"no '{key}:' in frontmatter")
    clean = " ".join(value.split())
    new_block = line_re.sub(f"{key}: {clean}", block, count=1)
    return text[: match.start(1)] + new_block + text[match.end(1) :]
