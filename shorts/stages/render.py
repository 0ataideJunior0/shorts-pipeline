from __future__ import annotations

from shorts.config import Config
from shorts.ideas import sync_idea_state
from shorts.project import Manifest, Project, sha256_file
from shorts.shell import CommandError, run_cmd
from shorts.stages.plan import warn_missing_categories


def run(project: Project, config: Config, *, force: bool = False) -> None:
    if not project.ideas_dir.is_dir():
        raise SystemExit(
            f"no ideas - run: python -m shorts ideate {project.name}"
        )

    manifest = Manifest.load(project.manifest_path)
    ideas = sync_idea_state(project, manifest)

    rendered = 0
    for slug, parsed in ideas:
        entry = manifest.get_idea(slug)
        if not parsed.approved:
            continue

        plan_meta = entry.get("plan") or {}
        plan_file = project.plan_file(slug)
        if not plan_meta or not plan_file.exists():
            print(
                f"render: {slug} has no plan - "
                f"run: python -m shorts plan {project.name}"
            )
            continue

        plan_hash = sha256_file(plan_file)
        render_meta = entry.get("render") or {}
        if (
            not force
            and render_meta.get("plan_sha256") == plan_hash
            and project.render_file(slug).exists()
        ):
            print(f"render: {slug} up to date, skipping")
            continue

        project.renders_dir.mkdir(parents=True, exist_ok=True)
        warn_missing_categories("render", slug, plan_file, config.assets_dir)
        try:
            run_cmd(
                [
                    "ai-vedit", "render",
                    "--plan", str(plan_file),
                    "--assets", str(config.assets_dir),
                    "--out", str(project.render_file(slug)),
                    "--aspect", config.aspect,
                ],
                cwd=project.renders_dir,
                capture=False,
            )
        except CommandError as exc:
            print(
                f"render: {slug} FAILED (ai-vedit exited {exc.returncode}) - "
                f"see output above"
            )
            continue

        manifest.set_idea(
            slug,
            render={
                "path": f"renders/{slug}.mp4",
                "plan_sha256": plan_hash,
            },
        )
        rendered += 1

    manifest.save(project.manifest_path)
    print(f"render: produced {rendered} video(s)")
