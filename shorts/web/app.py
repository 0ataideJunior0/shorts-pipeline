from __future__ import annotations

import json
import os
import queue
import sys
from pathlib import Path

from flask import Flask, Response, jsonify, request, send_from_directory

from shorts.config import Config
from shorts.web.edits import (
    EditError, apply_idea_edit, build_prompt_json, validate_plan_text,
)
from shorts.markdown import set_approved
from shorts.project import Project, slugify
from shorts.web.jobs import (
    ALLOWED_STAGES, JobBusy, JobRunner, _HEARTBEAT_SECONDS, sse_format, stage_argv,
)
from shorts.web.state import build_snapshot, category_report, list_projects

_STATIC = Path(__file__).parent / "static"


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

    @app.post("/api/jobs/current/cancel")
    def api_cancel():
        try:
            _runner().cancel()
        except JobBusy as exc:
            return _json_error(409, str(exc))
        return jsonify(_runner().state())

    return app
