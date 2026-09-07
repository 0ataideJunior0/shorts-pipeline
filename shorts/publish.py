from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from googleapiclient.errors import HttpError

from shorts.ideas import sync_idea_state
from shorts.markdown import parse_idea_file
from shorts.project import Manifest, sha256_file, utcnow_iso
from shorts.stages.plan import plan_opts_hash, subtitle_plan_args
from shorts.youtube import get_credentials, insert_video, youtube_service

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


def _http_reason(exc: HttpError) -> str:
    try:
        raw = exc.content.decode() if isinstance(exc.content, bytes) else exc.content
        err = (json.loads(raw) or {}).get("error", {})
        if err.get("errors"):
            return err["errors"][0].get("reason") or err.get("message", "")
        return err.get("message", "")
    except Exception:
        return getattr(exc, "reason", "") or str(exc)


def run(project, config, *, slugs: list[str] | None = None, force: bool = False) -> None:
    from shorts.web.state import idea_freshness

    manifest = Manifest.load(project.manifest_path)
    sync_idea_state(project, manifest)
    opts_hash = plan_opts_hash(
        min_beat_duration=config.render.min_beat_duration,
        subtitle_args=subtitle_plan_args(config.render.subtitle),
    )
    all_slugs = sorted(manifest.ideas)

    def eligible(s: str) -> bool:
        e = manifest.get_idea(s)
        if not e.get("approved"):
            return False
        return idea_freshness(project, s, manifest, opts_hash)["render"] == "fresh"

    candidates = [s for s in all_slugs if eligible(s)]
    if slugs:
        want = set(slugs)
        candidates = [s for s in candidates if s in want]
    if not force:
        candidates = [s for s in candidates if not manifest.get_idea(s).get("youtube")]

    if not candidates:
        print("publish: nothing to upload")
        return

    creds = get_credentials(config)
    service = youtube_service(creds)

    overrides: dict[str, datetime] = {}
    taken: set[datetime] = set()
    for s in all_slugs:
        e = manifest.get_idea(s)
        if e.get("publish_at"):
            overrides[s] = parse_iso(e["publish_at"])
            taken.add(overrides[s])
        yt = e.get("youtube") or {}
        if yt.get("publish_at"):
            taken.add(parse_iso(yt["publish_at"]))

    schedule = resolve_schedule(
        candidates,
        {s: overrides[s] for s in candidates if s in overrides},
        cadence_from_manifest(manifest.get_publish()),
        taken,
    )

    uploaded = failed = 0
    for s in candidates:
        parsed = parse_idea_file(project.idea_file(s).read_text(encoding="utf-8"))
        at = schedule[s]
        body = build_video_body(
            title=parsed.frontmatter.get("title", s),
            description=parsed.description,
            tags=parsed.tags,
            category_id=config.youtube.category_id,
            publish_at=at,
        )
        try:
            res = insert_video(service, mp4_path=project.render_file(s), body=body)
        except HttpError as exc:
            status = getattr(exc.resp, "status", None)
            reason = _http_reason(exc)
            print(f"publish: {s} FAILED {status} {reason}")
            failed += 1
            if status == 403 and "quota" in reason.lower():
                print(f"publish: quota exhausted - {uploaded} uploaded, rest deferred")
                break
            continue
        manifest.set_idea(s, youtube={
            "video_id": res["video_id"],
            "url": res["url"],
            "publish_at": iso(at) if at else None,
            "privacy": "private",
            "uploaded_at": utcnow_iso(),
            "title": body["snippet"]["title"],
        })
        manifest.save(project.manifest_path)
        uploaded += 1
        print(f"publish: {s} -> {res['url']}")

    print(f"publish: uploaded {uploaded} video(s)")
    if failed:
        raise SystemExit(1)
