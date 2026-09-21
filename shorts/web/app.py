from __future__ import annotations

import json
import os
import queue
import re
import sys
from pathlib import Path

from flask import Flask, Response, jsonify, request, send_from_directory

from shorts.config import Config
from shorts.web.edits import (
    EditError, apply_idea_edit, build_prompt_json, validate_plan_text,
)
from shorts.markdown import set_approved
from shorts.project import Manifest, Project, slugify
from shorts.web.jobs import (
    ALLOWED_STAGES, JobBusy, JobRunner, _HEARTBEAT_SECONDS, sse_format, stage_argv,
)
from shorts.web.state import build_snapshot, category_report, list_projects, publish_queue

_STATIC = Path(__file__).parent / "static"
_TIME_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")


def _atomic_write(path: Path, text: str) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def _json_error(status: int, message: str):
    return jsonify({"error": message}), status


def _load_project(config: Config, name: str) -> Project:
    return Project.load(config.projects_dir, name)


def create_app(config: Config) -> Flask:
    app = Flask(__name__, static_folder=None)
    runner = JobRunner(config.root)
    app.config["SHORTS_CONFIG"] = config
    app.config["JOB_RUNNER"] = runner

    def _runner():
        return app.config["JOB_RUNNER"]

    @app.get("/")
    def index():
        return send_from_directory(_STATIC, "index.html")

    @app.get("/api/projects")
    def api_projects():
        return jsonify(list_projects(config))

    @app.get("/api/projects/<name>")
    def api_project(name: str):
        try:
            project = _load_project(config, name)
        except FileNotFoundError:
            return _json_error(404, f"no such project: {name}")
        return _snapshot(project)

    @app.get("/api/jobs/current")
    def api_job_current():
        return jsonify(_runner().state())

    def _snapshot(project):
        try:
            snap = build_snapshot(project, config)
        except FileNotFoundError:
            # manifest.json not written yet (e.g. fetch subprocess still running)
            return _json_error(404, f"no such project: {project.name}")
        except (json.JSONDecodeError, KeyError):
            return _json_error(422, f"{project.name}/manifest.json is not valid JSON")
        snap["job"] = _runner().state() if _runner().running() else None
        return jsonify(snap)

    @app.put("/api/projects/<name>/prompt")
    def api_put_prompt(name: str):
        try:
            project = _load_project(config, name)
        except FileNotFoundError:
            return _json_error(404, f"no such project: {name}")
        body = request.get_json(silent=True) or {}
        try:
            content = build_prompt_json(str(body.get("prompt", "")))
        except EditError as exc:
            return _json_error(422, str(exc))
        project.ideas_dir.mkdir(parents=True, exist_ok=True)
        _atomic_write(project.prompt_path, content)
        return _snapshot(project)

    @app.put("/api/projects/<name>/ideas/<slug>")
    def api_put_idea(name: str, slug: str):
        try:
            project = _load_project(config, name)
        except FileNotFoundError:
            return _json_error(404, f"no such project: {name}")
        idea_path = project.idea_file(slug)
        if not idea_path.exists():
            return _json_error(404, f"no such idea: {slug}")
        body = request.get_json(silent=True) or {}
        try:
            new_text = apply_idea_edit(
                idea_path.read_text(encoding="utf-8"),
                title=str(body.get("title", "")),
                description=str(body.get("description", "")),
                tags=str(body.get("tags", "")),
                narration=str(body.get("narration", "")),
                approved=bool(body.get("approved", False)),
            )
        except EditError as exc:
            return _json_error(422, str(exc))
        _atomic_write(idea_path, new_text)
        return _snapshot(project)

    @app.put("/api/projects/<name>/ideas/<slug>/approved")
    def api_put_approved(name: str, slug: str):
        try:
            project = _load_project(config, name)
        except FileNotFoundError:
            return _json_error(404, f"no such project: {name}")
        idea_path = project.idea_file(slug)
        if not idea_path.exists():
            return _json_error(404, f"no such idea: {slug}")
        body = request.get_json(silent=True) or {}
        try:
            new_text = set_approved(
                idea_path.read_text(encoding="utf-8"), bool(body.get("approved", False))
            )
        except ValueError as exc:
            return _json_error(422, f"unexpected idea file format: {exc}")
        _atomic_write(idea_path, new_text)
        return _snapshot(project)

    @app.get("/api/projects/<name>/voice/<slug>")
    def api_voice(name: str, slug: str):
        try:
            project = _load_project(config, name)
        except FileNotFoundError:
            return _json_error(404, f"no such project: {name}")
        mp3 = project.voice_file(slug)
        if not mp3.exists():
            return _json_error(404, f"no audio for {slug}")
        return send_from_directory(
            project.voice_dir, mp3.name, mimetype="audio/mpeg", conditional=True
        )

    @app.get("/api/projects/<name>/categories")
    def api_categories(name: str):
        try:
            project = _load_project(config, name)
        except FileNotFoundError:
            return _json_error(404, f"no such project: {name}")
        return jsonify(category_report(project, config))

    @app.put("/api/projects/<name>/ideas/<slug>/plan")
    def api_put_plan(name: str, slug: str):
        try:
            project = _load_project(config, name)
        except FileNotFoundError:
            return _json_error(404, f"no such project: {name}")
        body = request.get_json(silent=True) or {}
        try:
            content = validate_plan_text(str(body.get("plan", "")))
        except EditError as exc:
            return _json_error(422, str(exc))
        project.renders_dir.mkdir(parents=True, exist_ok=True)
        _atomic_write(project.plan_file(slug), content)
        return _snapshot(project)

    _RUNNABLE = tuple(s for s in ALLOWED_STAGES if s != "fetch")

    @app.post("/api/projects")
    def api_new_project():
        body = request.get_json(silent=True) or {}
        url = str(body.get("url", "")).strip()
        name = str(body.get("name", "")).strip()
        if not url or not name:
            return _json_error(400, "url and name are required")
        slug = slugify(name)
        cmd = [sys.executable, "-m", "shorts",
               *stage_argv("fetch", slug, url=url, force=bool(body.get("force")))]
        try:
            _runner().start("fetch", slug, cmd)
        except JobBusy as exc:
            return _json_error(409, str(exc))
        return jsonify(_runner().state()), 202

    @app.post("/api/projects/<name>/run/<stage>")
    def api_run_stage(name: str, stage: str):
        if stage not in _RUNNABLE:
            return _json_error(400, f"cannot run stage: {stage}")
        try:
            _load_project(config, name)
        except FileNotFoundError:
            return _json_error(404, f"no such project: {name}")
        body = request.get_json(silent=True) or {}
        cmd = [sys.executable, "-m", "shorts",
               *stage_argv(stage, name, force=bool(body.get("force")))]
        try:
            _runner().start(stage, name, cmd)
        except JobBusy as exc:
            return _json_error(409, str(exc))
        return jsonify(_runner().state()), 202

    @app.get("/api/jobs/current/stream")
    def api_stream():
        runner = _runner()

        def gen():
            q = runner.attach()
            try:
                while True:
                    try:
                        event = q.get(timeout=_HEARTBEAT_SECONDS)
                    except queue.Empty:
                        yield ": heartbeat\n\n"
                        continue
                    if event is None:
                        return
                    yield sse_format(event)
            finally:
                runner.detach(q)

        return Response(gen(), mimetype="text/event-stream", headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        })

    @app.get("/api/youtube/status")
    def api_youtube_status():
        from shorts.youtube import channel_title, get_credentials, YouTubeAuthError

        if not config.youtube.client_secret and not config.youtube.token_path.exists():
            return jsonify({"connected": False, "channel": None, "error": "not configured"})
        try:
            creds = get_credentials(config)
        except YouTubeAuthError as exc:
            err = "token expired" if getattr(exc, "reason", "") == "expired" else "not connected"
            return jsonify({"connected": False, "channel": None, "error": err})
        try:
            ch = channel_title(creds)
        except Exception:
            ch = None
        return jsonify({"connected": True, "channel": ch, "error": None})

    @app.post("/api/youtube/auth")
    def api_youtube_auth():
        cmd = [sys.executable, "-m", "shorts", *stage_argv("youtube-auth", "")]
        try:
            _runner().start("youtube-auth", "", cmd)
        except JobBusy as exc:
            return _json_error(409, str(exc))
        return jsonify(_runner().state()), 202

    @app.get("/api/projects/<name>/publish")
    def api_publish_queue(name: str):
        try:
            project = _load_project(config, name)
        except FileNotFoundError:
            return _json_error(404, f"no such project: {name}")
        return jsonify(publish_queue(project, config))

    @app.put("/api/projects/<name>/publish/cadence")
    def api_put_cadence(name: str):
        # function-local on purpose: shorts.publish imports googleapiclient at module scope
        from shorts.publish import parse_iso
        try:
            project = _load_project(config, name)
        except FileNotFoundError:
            return _json_error(404, f"no such project: {name}")
        body = request.get_json(silent=True) or {}
        manifest = Manifest.load(project.manifest_path)
        start = body.get("start")
        if not start:
            manifest.publish = {}
        else:
            try:
                parse_iso(str(start))
            except ValueError:
                return _json_error(422, "start must be an ISO datetime")
            try:
                interval = int(body.get("interval_hours") or 24)
            except (TypeError, ValueError):
                return _json_error(422, "interval_hours must be an integer")
            if interval <= 0:
                return _json_error(422, "interval_hours must be > 0")
            weekdays = body.get("weekdays")
            if weekdays is not None:
                if not isinstance(weekdays, list) or not all(
                    type(d) is int and 1 <= d <= 7 for d in weekdays
                ):
                    return _json_error(422, "weekdays must be integers 1..7")
                weekdays = list(weekdays) or None
            times = body.get("times")
            cleaned_times = None
            if times is not None:
                if not isinstance(times, list):
                    return _json_error(422, "times must be a list of HH:MM strings")
                cleaned_times_set = set()
                for t in times:
                    if not isinstance(t, str):
                        return _json_error(422, "times must be a list of HH:MM strings")
                    m = _TIME_RE.match(t.strip())
                    if not m:
                        return _json_error(422, "times must be a list of HH:MM strings")
                    cleaned_times_set.add(f"{int(m.group(1)):02d}:{int(m.group(2)):02d}")
                cleaned_times = sorted(cleaned_times_set)

            pub = {
                "start": str(start),
                "interval_hours": interval,
                "weekdays": weekdays,
            }
            if times is not None:
                pub["times"] = cleaned_times
            manifest.publish = pub
        manifest.save(project.manifest_path)
        return jsonify(publish_queue(project, config))

    @app.put("/api/projects/<name>/ideas/<slug>/publish-at")
    def api_put_publish_at(name: str, slug: str):
        # function-local on purpose: shorts.publish imports googleapiclient at module scope
        from shorts.publish import parse_iso
        try:
            project = _load_project(config, name)
        except FileNotFoundError:
            return _json_error(404, f"no such project: {name}")
        if not project.idea_file(slug).exists():
            return _json_error(404, f"no such idea: {slug}")
        body = request.get_json(silent=True) or {}
        manifest = Manifest.load(project.manifest_path)
        pa = body.get("publish_at")
        if pa is None:
            entry = manifest.get_idea(slug)
            entry.pop("publish_at", None)
            manifest.ideas[slug] = entry
        else:
            try:
                parse_iso(str(pa))
            except ValueError:
                return _json_error(422, "publish_at must be an ISO datetime")
            manifest.set_idea(slug, publish_at=str(pa))
        manifest.save(project.manifest_path)
        return jsonify(publish_queue(project, config))

    def _start_publish(name, slugs):
        cmd = [sys.executable, "-m", "shorts",
               *stage_argv("publish", name, slugs=slugs)]
        try:
            _runner().start("publish", name, cmd)
        except JobBusy as exc:
            return _json_error(409, str(exc))
        return jsonify(_runner().state()), 202

    @app.post("/api/projects/<name>/publish")
    def api_publish_all(name: str):
        try:
            _load_project(config, name)
        except FileNotFoundError:
            return _json_error(404, f"no such project: {name}")
        return _start_publish(name, None)

    @app.post("/api/projects/<name>/ideas/<slug>/publish")
    def api_publish_one(name: str, slug: str):
        try:
            _load_project(config, name)
        except FileNotFoundError:
            return _json_error(404, f"no such project: {name}")
        return _start_publish(name, [slug])

    @app.post("/api/jobs/current/cancel")
    def api_cancel():
        try:
            _runner().cancel()
        except JobBusy as exc:
            return _json_error(409, str(exc))
        return jsonify(_runner().state())

    return app
