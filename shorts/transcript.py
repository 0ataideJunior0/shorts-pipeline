from __future__ import annotations

import math
import re
from dataclasses import dataclass


@dataclass
class Segment:
    start: float
    end: float
    text: str


def chunk_plan(total_seconds: float, chunk_seconds: float) -> list[tuple[float, float]]:
    if total_seconds <= 0:
        raise ValueError("total_seconds must be positive")
    if chunk_seconds <= 0:
        raise ValueError("chunk_seconds must be positive")
    count = max(1, math.ceil(total_seconds / chunk_seconds))
    out: list[tuple[float, float]] = []
    for i in range(count):
        start = i * chunk_seconds
        if start >= total_seconds:
            break
        end = min(total_seconds, start + chunk_seconds)
        out.append((float(start), float(end)))
    return out


def shift_segments(segments: list[Segment], offset: float) -> list[Segment]:
    return [Segment(s.start + offset, s.end + offset, s.text) for s in segments]


def stitch(chunk_results: list[tuple[float, list[Segment]]]) -> list[Segment]:
    combined: list[Segment] = []
    for offset, segments in chunk_results:
        combined.extend(shift_segments(segments, offset))
    combined.sort(key=lambda s: s.start)
    return combined


_WS_RE = re.compile(r"\s+")


def segments_to_text(segments: list[Segment]) -> str:
    joined = " ".join(s.text.strip() for s in segments if s.text.strip())
    return _WS_RE.sub(" ", joined).strip()
