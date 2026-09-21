from __future__ import annotations

from shorts.config import Config
from shorts.ideas import sync_idea_state
from shorts.markdown import parse_idea_file, prefixed_slug, render_idea
from shorts.openai_helpers import generate_ideas, get_client
from shorts.project import Manifest, Project, sha256_file, sha256_text
from shorts.prompt import PromptError, ensure_prompt_file, read_prompt


def run(
    project: Project,
    config: Config,
    *,
    force: bool = False,
    count: int | None = None,
) -> None:
    if not project.transcript_txt_path.exists():
        raise SystemExit(
            f"no transcript - run: python -m shorts transcribe {project.name}"
        )

    manifest = Manifest.load(project.manifest_path)
    ensure_prompt_file(project)
    try:
        prompt_text = read_prompt(project)
    except PromptError as exc:
        raise SystemExit(str(exc))
    prompt_hash = sha256_text(prompt_text)

    if manifest.is_stage_done("ideate") and not force:
        prev = manifest.get_stage("ideate") or {}
        sync_idea_state(project, manifest)
        manifest.save(project.manifest_path)
        if prev.get("prompt_sha256") not in (None, prompt_hash):
            print(
                "ideate: prompt.json changed since last ideate - "
                "run with --force to regenerate"
            )
        else:
            print(
                "ideate: already generated; refreshed idea state. "
                "Use --force to regenerate."
            )
        return

    if count is not None and count > 0:
        effective_count = count
    else:
        manifest_count = manifest.get_setting("count")
        if (
            manifest_count is not None
            and isinstance(manifest_count, int)
            and not isinstance(manifest_count, bool)
            and manifest_count > 0
        ):
            effective_count = manifest_count
        else:
            effective_count = config.ideate.count

    transcript = project.transcript_txt_path.read_text()
    title = manifest.source.get("title", project.name)
    client = get_client(config.openai_api_key)
    ideas = generate_ideas(
        client,
        transcript_text=transcript,
        video_title=title,
        prompt=prompt_text,
        model=config.ideate.model,
        count=effective_count,
    )

    project.ideas_dir.mkdir(parents=True, exist_ok=True)
    written = 0
    for index, idea in enumerate(ideas, start=1):
        pslug = prefixed_slug(index, idea.slug)
        path = project.idea_file(pslug)
        if path.exists() and not force:
            continue
        text = render_idea(idea, index)
        path.write_text(text)
        parsed = parse_idea_file(text)
        manifest.set_idea(
            pslug,
            approved=parsed.approved,
            script_sha256=sha256_text(parsed.narration),
        )
        written += 1

    manifest.stage_done(
        "ideate",
        model=config.ideate.model,
        transcript_sha256=sha256_file(project.transcript_txt_path),
        prompt_sha256=prompt_hash,
        count=effective_count,
    )
    manifest.save(project.manifest_path)
    print(f"ideate: wrote {written} idea file(s) -> {project.ideas_dir}")
