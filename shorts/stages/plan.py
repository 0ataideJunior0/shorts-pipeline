from __future__ import annotations

import json
import shutil

from shorts.config import Config, SubtitleCfg
from shorts.ideas import sync_idea_state
from shorts.project import Manifest, Project, sha256_text
from shorts.shell import CommandError, run_cmd


def subtitle_plan_args(sub: SubtitleCfg) -> list[str]:
    """`ai-vedit plan` subtitle flags for the given config.

    Returns `[]` when subtitles are disabled; otherwise `--subtitles` plus one
    flag per styling option that is set (an unset option is left off so
    `ai-vedit` applies its own default).
    """
    if not sub.enabled:
        return []
    args = ["--subtitles"]
    if sub.font:
        args += ["--subtitle-font", sub.font]
    if sub.font_size is not None:
        args += ["--subtitle-font-size", str(sub.font_size)]
    if sub.primary_color:
        args += ["--subtitle-primary-color", sub.primary_color]
    if sub.bold:
        args.append("--subtitle-bold")
    if sub.italic:
        args.append("--subtitle-italic")
    if sub.uppercase:
        args.append("--subtitle-uppercase")
    if sub.position:
        args += ["--subtitle-position", sub.position]
    if sub.margin_vertical is not None:
        args += ["--subtitle-margin-vertical", str(sub.margin_vertical)]
    if sub.max_chars_per_line is not None:
        args += ["--subtitle-max-chars-per-line", str(sub.max_chars_per_line)]
    if sub.max_lines is not None:
        args += ["--subtitle-max-lines", str(sub.max_lines)]
    if sub.max_duration is not None:
        args += ["--subtitle-max-duration", str(sub.max_duration)]
    return args


def plan_opts_hash(*, min_beat_duration: float, subtitle_args: list[str]) -> str:
    """Digest of the `ai-vedit plan` options that change the produced plan.json.

    Folded into the plan staleness check so changing `min_beat_duration` or any
    `[render.subtitle]` setting regenerates the plan on the next run without
    `--force`.
    """
    return sha256_text(
        f"{float(min_beat_duration):.4f}\n" + " ".join(subtitle_args)
    )


def plan_categories(plan_path) -> list[str]:
    """Every asset category the plan references, sorted and de-duplicated."""
    data = json.loads(plan_path.read_text())
    cats: set[str] = set()
    for beat in data.get("beats", []):
        category = beat.get("category")
        if category:
            cats.add(category)
    return sorted(cats)


def warn_missing_categories(stage: str, slug: str, plan_path, assets_dir) -> None:
    """Print a warning listing plan categories with no folder under assets_dir."""
    missing = [c for c in plan_categories(plan_path) if not (assets_dir / c).is_dir()]
    if missing:
        print(
            f"{stage}: {slug} WARNING - plan references asset categories with "
            f"no folder in {assets_dir}: {', '.join(missing)} "
            f"(ai-vedit will use its general/ fallback)"
        )


def run(project: Project, config: Config, *, force: bool = False) -> None:
    if not project.ideas_dir.is_dir():
        raise SystemExit(
            f"no ideas - run: python -m shorts ideate {project.name}"
        )

    manifest = Manifest.load(project.manifest_path)
    ideas = sync_idea_state(project, manifest)

    sub_args = subtitle_plan_args(config.render.subtitle)
    opts_hash = plan_opts_hash(
        min_beat_duration=config.render.min_beat_duration,
        subtitle_args=sub_args,
    )

    planned = 0
    for slug, parsed in ideas:
        entry = manifest.get_idea(slug)
        if not parsed.approved:
            continue

        voice_meta = entry.get("voice") or {}
        mp3 = project.voice_file(slug)
        if not mp3.exists() or not voice_meta:
            print(
                f"plan: {slug} has no narration audio - "
                f"run: python -m shorts voice {project.name}"
            )
            continue

        voice_hash = voice_meta.get("script_sha256")
        voice_params_hash = voice_meta.get("params_sha256")
        plan_meta = entry.get("plan") or {}
        plan_dst = project.plan_file(slug)
        if (
            not force
            and plan_meta.get("script_sha256") == voice_hash
            and plan_meta.get("voice_params_sha256") == voice_params_hash
            and plan_meta.get("opts_sha256") == opts_hash
            and plan_dst.exists()
        ):
            print(f"plan: {slug} up to date, skipping")
            continue

        project.renders_dir.mkdir(parents=True, exist_ok=True)
        # `ai-vedit plan` always writes `plan.json` into its working directory.
        produced = project.renders_dir / "plan.json"
        produced.unlink(missing_ok=True)
        cmd = [
            "ai-vedit", "plan",
            "--audio", str(mp3),
            "--assets", str(config.assets_dir),
            "--min-beat-duration", str(config.render.min_beat_duration),
            *sub_args,
        ]
        try:
            run_cmd(cmd, cwd=project.renders_dir, capture=False)
        except CommandError as exc:
            print(
                f"plan: {slug} FAILED (ai-vedit exited {exc.returncode}) - "
                f"see output above"
            )
            continue
        if not produced.exists():
            print(f"plan: {slug} FAILED - ai-vedit plan produced no plan.json")
            continue
        shutil.move(str(produced), str(plan_dst))

        warn_missing_categories("plan", slug, plan_dst, config.assets_dir)

        manifest.set_idea(
            slug,
            plan={
                "path": f"renders/{slug}.plan.json",
                "script_sha256": voice_hash,
                "voice_params_sha256": voice_params_hash,
                "opts_sha256": opts_hash,
            },
        )
        planned += 1

    manifest.save(project.manifest_path)
    print(
        f"plan: wrote {planned} plan(s) -> {project.renders_dir}\n"
        f"review renders/*.plan.json, then: python -m shorts render {project.name}"
    )
