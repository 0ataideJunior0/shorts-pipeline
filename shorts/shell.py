from __future__ import annotations

import subprocess
from pathlib import Path


class CommandError(Exception):
    def __init__(self, cmd: list, returncode: int, stderr: str) -> None:
        self.cmd = cmd
        self.returncode = returncode
        self.stderr = stderr
        joined = " ".join(str(part) for part in cmd)
        super().__init__(f"command failed ({returncode}): {joined}\n{stderr}".rstrip())


def run_cmd(
    args: list, *, capture: bool = True, cwd: "Path | str | None" = None
) -> subprocess.CompletedProcess:
    proc = subprocess.run(
        [str(part) for part in args],
        capture_output=capture,
        text=True,
        cwd=str(cwd) if cwd is not None else None,
    )
    if proc.returncode != 0:
        raise CommandError(args, proc.returncode, (proc.stderr or "").strip())
    return proc


def ffprobe_duration(path: Path) -> float:
    proc = run_cmd(
        [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(path),
        ]
    )
    return float(proc.stdout.strip())
