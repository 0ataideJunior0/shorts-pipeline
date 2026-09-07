from __future__ import annotations

import os
from pathlib import Path

from flask import Flask, jsonify, send_from_directory

from shorts.config import Config
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

    return app
