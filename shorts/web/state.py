from __future__ import annotations

import json
from pathlib import Path

from shorts.config import Config
from shorts.ideas import sync_idea_state
from shorts.project import Manifest, Project, sha256_file
from shorts.prompt import DEFAULT_IDEATE_PROMPT
from shorts.stages.plan import plan_opts_hash, subtitle_plan_args


def _opts_hash(config: Config) -> str:
    return plan_opts_hash(
        min_beat_duration=config.render.min_beat_duration,
        subtitle_args=subtitle_plan_args(config.render.subtitle),
    )


def prompt_text(project: Project) -> str:
    path = project.prompt_path
    if not path.exists():
        return DEFAULT_IDEATE_PROMPT
    raw = path.read_text(encoding="utf-8")
    try:
        data = json.loads(raw)
        value = str(data["prompt"]) if isinstance(data, dict) else ""
        return value or raw
    except (json.JSONDecodeError, KeyError):
        return raw


def idea_freshness(
    project: Project, slug: str, manifest: Manifest, opts_hash: str
) -> dict:
    idea = manifest.get_idea(slug)
    script = idea.get("script_sha256")

    voice = idea.get("voice") or {}
    if not voice or not project.voice_file(slug).exists():
        voice_state = "missing"
    elif voice.get("script_sha256") == script:
        voice_state = "fresh"
    else:
        voice_state = "stale"

    plan = idea.get("plan") or {}
    plan_file = project.plan_file(slug)
    if not plan or not plan_file.exists():
        plan_state = "missing"
    elif (
        plan.get("script_sha256") == voice.get("script_sha256")
        and plan.get("voice_params_sha256") == voice.get("params_sha256")
        and plan.get("opts_sha256") == opts_hash
    ):
        plan_state = "fresh"
    else:
        plan_state = "stale"

    render = idea.get("render") or {}
    if not render or not project.render_file(slug).exists():
        render_state = "missing"
    elif plan_file.exists() and render.get("plan_sha256") == sha256_file(plan_file):
        render_state = "fresh"
    else:
        render_state = "stale"

    return {"voice": voice_state, "plan": plan_state, "render": render_state}


def _agg(states: list[str]) -> str:
    """done if all fresh, else stale.

    The empty-list branch is a defensive fallback: every call site guards on a
    non-empty list before calling this, so ``"ready"`` is not returned in normal
    flow.
    """
    if not states:
        return "ready"
    return "done" if all(s == "fresh" for s in states) else "stale"


def stage_rows(
    project: Project, manifest: Manifest, config: Config
) -> list[dict]:
    opts_hash = _opts_hash(config)
    slugs = sorted(manifest.ideas)
    approved = [s for s in slugs if manifest.get_idea(s).get("approved")]
    fr = {s: idea_freshness(project, s, manifest, opts_hash) for s in slugs}

    def at(stage: str):
        return (manifest.get_stage(stage) or {}).get("at")

    rows: list[dict] = []

    # fetch
    if manifest.is_stage_done("fetch") and project.video_path.exists():
        rows.append({"stage": "fetch", "status": "done", "at": at("fetch"), "detail": ""})
    else:
        rows.append({"stage": "fetch", "status": "ready", "at": at("fetch"),
                     "detail": "no source video"})
    fetch_done = rows[-1]["status"] == "done"

    # transcribe
    if not fetch_done:
        rows.append({"stage": "transcribe", "status": "blocked", "at": at("transcribe"),
                     "detail": "needs fetch"})
    elif not (manifest.is_stage_done("transcribe") and project.transcript_txt_path.exists()):
        rows.append({"stage": "transcribe", "status": "ready", "at": at("transcribe"),
                     "detail": ""})
    else:
        recorded = (manifest.get_stage("transcribe") or {}).get("audio_sha256")
        current = sha256_file(project.audio_path) if project.audio_path.exists() else recorded
        status = "done" if recorded == current else "stale"
        rows.append({"stage": "transcribe", "status": status, "at": at("transcribe"),
                     "detail": "" if status == "done" else "audio changed"})
    transcribe_done = rows[-1]["status"] == "done"

    # ideate
    if not transcribe_done:
        rows.append({"stage": "ideate", "status": "blocked", "at": at("ideate"),
                     "detail": "needs transcribe"})
    elif not manifest.is_stage_done("ideate"):
        rows.append({"stage": "ideate", "status": "ready", "at": at("ideate"), "detail": ""})
    else:
        recorded = (manifest.get_stage("ideate") or {}).get("prompt_sha256")
        from shorts.project import sha256_text
        current = sha256_text(prompt_text(project))
        status = "done" if recorded in (None, current) else "stale"
        rows.append({"stage": "ideate", "status": status, "at": at("ideate"),
                     "detail": f"{len(slugs)} ideas" if status == "done"
                     else "prompt.json changed"})
    ideate_done = rows[-1]["status"] == "done"

    # voice
    if not ideate_done:
        rows.append({"stage": "voice", "status": "blocked", "at": at("voice"),
                     "detail": "needs ideate"})
    elif not approved:
        rows.append({"stage": "voice", "status": "ready", "at": at("voice"),
                     "detail": "no approved ideas"})
    else:
        states = [fr[s]["voice"] for s in approved]
        status = _agg(states)
        need = sum(1 for x in states if x != "fresh")
        rows.append({"stage": "voice", "status": status, "at": at("voice"),
                     "detail": "" if status == "done"
                     else f"{need} of {len(approved)} approved need audio"})

    # plan
    have_voice = [s for s in approved if fr[s]["voice"] == "fresh"]
    if not ideate_done:
        rows.append({"stage": "plan", "status": "blocked", "at": at("plan"),
                     "detail": "needs ideate"})
    elif not have_voice:
        rows.append({"stage": "plan", "status": "blocked", "at": at("plan"),
                     "detail": "needs voice"})
    else:
        states = [fr[s]["plan"] for s in have_voice]
        status = _agg(states)
        need = sum(1 for x in states if x != "fresh")
        rows.append({"stage": "plan", "status": status, "at": at("plan"),
                     "detail": "" if status == "done"
                     else f"{need} of {len(have_voice)} need a plan"})

    # render
    have_plan = [s for s in have_voice if fr[s]["plan"] in ("fresh", "stale")]
    if not have_plan:
        rows.append({"stage": "render", "status": "blocked", "at": at("render"),
                     "detail": "needs plan"})
    else:
        states = [fr[s]["render"] for s in have_plan]
        status = _agg(states)
        need = sum(1 for x in states if x != "fresh")
        rows.append({"stage": "render", "status": status, "at": at("render"),
                     "detail": "" if status == "done"
                     else f"{need} of {len(have_plan)} need a render"})

    return rows


def build_snapshot(project: Project, config: Config) -> dict:
    manifest = Manifest.load(project.manifest_path)
    parsed = dict(sync_idea_state(project, manifest))
    manifest.save(project.manifest_path)
    opts_hash = _opts_hash(config)

    ideas = []
    for slug in sorted(manifest.ideas):
        idea = manifest.get_idea(slug)
        p = parsed.get(slug)
        plan_file = project.plan_file(slug)
        plan_json = None
        if plan_file.exists():
            try:
                plan_json = json.loads(plan_file.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                plan_json = None
        fr = idea_freshness(project, slug, manifest, opts_hash)
        ideas.append({
            "slug": slug,
            "title": (p.frontmatter.get("title") if p else "") or slug,
            "approved": bool(idea.get("approved")),
            "narration": p.narration if p else "",
            "voice": fr["voice"],
            "plan": fr["plan"],
            "render": fr["render"],
            "plan_json": plan_json,
        })

    return {
        "name": project.name,
        "source": {
            "url": manifest.source.get("url", ""),
            "title": manifest.source.get("title", ""),
            "video_id": manifest.source.get("video_id", ""),
        },
        "stages": stage_rows(project, manifest, config),
        "prompt": prompt_text(project),
        "ideas": ideas,
        "job": None,
    }


def list_projects(config: Config) -> list[dict]:
    out = []
    for project in Project.list_all(config.projects_dir):
        try:
            manifest = Manifest.load(project.manifest_path)
            rows = stage_rows(project, manifest, config)
        except (json.JSONDecodeError, KeyError, FileNotFoundError):
            # a single corrupt/missing manifest.json must not 500 the whole list
            continue
        out.append({
            "name": project.name,
            "title": manifest.source.get("title", ""),
            "updated_at": _mtime_iso(project.manifest_path),
            "stages": {r["stage"]: r["status"] for r in rows},
        })
    return out


def _mtime_iso(path: Path) -> str:
    from datetime import datetime, timezone
    ts = path.stat().st_mtime
    return datetime.fromtimestamp(ts, timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
