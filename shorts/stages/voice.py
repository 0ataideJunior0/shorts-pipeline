from __future__ import annotations

from shorts.config import Config
from shorts.ideas import sync_idea_state
from shorts.openai_helpers import get_client, synthesize_speech, voice_params_hash
from shorts.project import Manifest, Project


def run(project: Project, config: Config, *, force: bool = False) -> None:
    if not project.ideas_dir.is_dir():
        raise SystemExit(
            f"no ideas - run: python -m shorts ideate {project.name}"
        )

    manifest = Manifest.load(project.manifest_path)
    ideas = sync_idea_state(project, manifest)

    params_hash = voice_params_hash(
        model=config.voice.model,
        voice=config.voice.voice,
        instructions=config.voice.instructions,
        speed=config.voice.speed,
    )

    client = None
    made = 0
    for slug, parsed in ideas:
        entry = manifest.get_idea(slug)
        if not parsed.approved:
            print(f"voice: {slug} not approved, skipping")
            continue
        if not parsed.narration.strip():
            print(f"voice: {slug} has empty narration, skipping")
            continue

        script_hash = entry["script_sha256"]
        voice_meta = entry.get("voice") or {}
        if (
            not force
            and voice_meta.get("script_sha256") == script_hash
            and voice_meta.get("params_sha256") == params_hash
            and project.voice_file(slug).exists()
        ):
            print(f"voice: {slug} up to date, skipping")
            continue

        project.voice_dir.mkdir(parents=True, exist_ok=True)
        if client is None:
            client = get_client(config.openai_api_key)
        print(f"voice: synthesizing {slug}")
        synthesize_speech(
            client,
            text=parsed.narration,
            out_path=project.voice_file(slug),
            model=config.voice.model,
            voice=config.voice.voice,
            instructions=config.voice.instructions,
            speed=config.voice.speed,
        )
        manifest.set_idea(
            slug,
            voice={
                "path": f"voice/{slug}.mp3",
                "script_sha256": script_hash,
                "params_sha256": params_hash,
            },
        )
        made += 1

    manifest.save(project.manifest_path)
    print(f"voice: generated {made} narration file(s)")
