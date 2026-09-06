from __future__ import annotations

import json
import math

from shorts.config import Config
from shorts.openai_helpers import get_client, transcribe_audio
from shorts.project import Manifest, Project, sha256_file
from shorts.shell import ffprobe_duration, run_cmd
from shorts.transcript import Segment, chunk_plan, segments_to_text, stitch

_MAX_BYTES = 24 * 1024 * 1024


def _extract_audio(project: Project) -> None:
    project.audio_dir.mkdir(parents=True, exist_ok=True)
    run_cmd(
        [
            "ffmpeg", "-y",
            "-i", str(project.video_path),
            "-vn", "-ac", "1", "-ar", "16000", "-b:a", "48k",
            str(project.audio_path),
        ]
    )


def run(project: Project, config: Config, *, force: bool = False) -> None:
    if not project.video_path.exists():
        raise SystemExit("no source video - run: python -m shorts fetch <url>")

    manifest = Manifest.load(project.manifest_path)

    if not project.audio_path.exists() or force:
        _extract_audio(project)

    audio_hash = sha256_file(project.audio_path)
    prev = manifest.get_stage("transcribe") or {}
    if (
        not force
        and prev.get("status") == "done"
        and prev.get("audio_sha256") == audio_hash
        and project.transcript_json_path.exists()
    ):
        print("transcribe: up to date, skipping")
        return

    client = get_client(config.openai_api_key)
    size = project.audio_path.stat().st_size
    duration = ffprobe_duration(project.audio_path)

    if size <= _MAX_BYTES:
        chunks = [(0.0, duration)]
    else:
        parts = math.ceil(size / _MAX_BYTES)
        chunks = chunk_plan(duration, duration / parts)

    project.transcript_dir.mkdir(parents=True, exist_ok=True)
    chunk_results: list[tuple[float, list[Segment]]] = []
    for idx, (start, end) in enumerate(chunks):
        if len(chunks) == 1:
            part_path = project.audio_path
        else:
            part_path = project.transcript_dir / f".chunk-{idx:03d}.mp3"
            run_cmd(
                [
                    "ffmpeg", "-y",
                    "-ss", f"{start}", "-to", f"{end}",
                    "-i", str(project.audio_path),
                    "-ac", "1", "-ar", "16000", "-b:a", "48k",
                    str(part_path),
                ]
            )
        print(f"transcribe: chunk {idx + 1}/{len(chunks)} ({start:.0f}-{end:.0f}s)")
        segments = transcribe_audio(client, part_path, config.transcribe.model)
        chunk_results.append((start, segments))
        if part_path != project.audio_path:
            part_path.unlink(missing_ok=True)

    segments = stitch(chunk_results)
    project.transcript_json_path.write_text(
        json.dumps(
            [{"start": s.start, "end": s.end, "text": s.text} for s in segments],
            indent=2,
            ensure_ascii=False,
        )
        + "\n"
    )
    project.transcript_txt_path.write_text(segments_to_text(segments) + "\n")

    manifest.stage_done(
        "transcribe",
        model=config.transcribe.model,
        audio_sha256=audio_hash,
        outputs=["transcript/transcript.json", "transcript/transcript.txt"],
    )
    manifest.save(project.manifest_path)
    print(f"transcribe: {len(segments)} segments -> {project.transcript_txt_path}")
