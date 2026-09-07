from __future__ import annotations

from datetime import datetime, timedelta, timezone

_K_CAP = 3650


def parse_iso(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def cadence_from_manifest(pub: dict) -> dict | None:
    if not pub or not pub.get("start"):
        return None
    return {
        "start": parse_iso(pub["start"]),
        "interval_hours": int(pub.get("interval_hours", 24)),
        "weekdays": pub.get("weekdays"),
    }


def build_video_body(
    *,
    title: str,
    description: str,
    tags: str,
    category_id: int,
    publish_at: datetime | None,
) -> dict:
    body = {
        "snippet": {
            "title": title[:100],
            "description": description,
            "tags": [t.strip() for t in tags.split(",") if t.strip()],
            "categoryId": str(category_id),
        },
        "status": {"privacyStatus": "private", "selfDeclaredMadeForKids": False},
    }
    if publish_at is not None:
        body["status"]["publishAt"] = iso(publish_at)
    return body


def resolve_schedule(
    slugs: list[str],
    overrides: dict[str, datetime],
    cadence: dict | None,
    taken: set[datetime],
) -> dict[str, datetime | None]:
    used = set(taken)
    out: dict[str, datetime | None] = {}
    k = 0
    start = cadence["start"] if cadence else None
    interval = timedelta(hours=cadence["interval_hours"]) if cadence else None
    weekdays = cadence["weekdays"] if cadence else None
    for slug in slugs:
        if slug in overrides:
            out[slug] = overrides[slug]
            used.add(overrides[slug])
            continue
        if start is None:
            out[slug] = None
            continue
        chosen = None
        while k < _K_CAP:
            slot = start + interval * k
            k += 1
            if slot in used:
                continue
            if weekdays is not None and slot.isoweekday() not in weekdays:
                continue
            chosen = slot
            break
        out[slug] = chosen
        if chosen is not None:
            used.add(chosen)
    return out
