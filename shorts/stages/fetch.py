from __future__ import annotations

import json
import sys

from shorts.config import Config
from shorts.project import Manifest, Project
from shorts.prompt import ensure_prompt_file
from shorts.shell import run_cmd


def probe_title(url: str) -> str:
    proc = run_cmd(
        [sys.executable, "-m", "yt_dlp", "--skip-download", "--print", "title", url]
    )
    return proc.stdout.strip().splitlines()[0]


def run(project: Project, config: Config, *, url: str, force: bool = False) -> None:
    project.ensure_dirs()
    ensure_prompt_file(project)

    if project.video_path.exists() and not force:
        print(f"fetch: {project.video_path} already present, skipping (use --force)")
        return

    run_cmd(
        [
            sys.executable, "-m", "yt_dlp",
            "-f", "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/b",
            "--merge-output-format", "mp4",
            "--write-info-json",
            "--no-playlist",
            "-o", str(project.source_dir / "video.%(ext)s"),
            url,
        ],
        capture=False,
    )

    info: dict = {}
    if project.info_json_path.exists():
        info = json.loads(project.info_json_path.read_text())

    manifest = (
        Manifest.load(project.manifest_path)
        if project.manifest_path.exists()
        else Manifest.new(project.name)
    )
    manifest.source = {
        "url": url,
        "video_id": info.get("id", ""),
        "title": info.get("title", project.name),
    }
    manifest.stage_done("fetch", outputs=["source/video.mp4"])
    manifest.save(project.manifest_path)
    print(f"fetch: downloaded -> {project.video_path}")
