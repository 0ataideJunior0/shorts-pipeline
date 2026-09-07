from __future__ import annotations

import os
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

from shorts.config import Config
from shorts.web.edits import (
    EditError, apply_idea_edit, build_prompt_json, validate_plan_text,
)
from shorts.project import Project
from shorts.web.jobs import JobRunner
from shorts.web.state import build_snapshot, list_projects

_STATIC = Path(__file__).parent / "static"


def _atomic_write(path: Path, text: str) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text)
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
        snap = build_snapshot(project, config)
        snap["job"] = runner.state() if runner.running() else None
        return jsonify(snap)

    @app.get("/api/jobs/current")
    def api_job_current():
        return jsonify(runner.state())

    def _snapshot(project):
        snap = build_snapshot(project, config)
        snap["job"] = runner.state() if runner.running() else None
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
                idea_path.read_text(),
                narration=str(body.get("narration", "")),
                approved=bool(body.get("approved", False)),
            )
        except EditError as exc:
            return _json_error(422, str(exc))
        _atomic_write(idea_path, new_text)
        return _snapshot(project)

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

    return app
