from __future__ import annotations

from shorts.markdown import ParsedIdea, parse_idea_file
from shorts.project import Manifest, Project, sha256_text


def sync_idea_state(
    project: Project, manifest: Manifest
) -> list[tuple[str, ParsedIdea]]:
    result: list[tuple[str, ParsedIdea]] = []
    if not project.ideas_dir.is_dir():
        return result
    for path in sorted(project.ideas_dir.glob("*.md")):
        parsed = parse_idea_file(path.read_text())
        slug = parsed.slug or path.stem
        manifest.set_idea(
            slug,
            approved=parsed.approved,
            script_sha256=sha256_text(parsed.narration),
        )
        result.append((slug, parsed))
    return result
