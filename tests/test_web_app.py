import json
from pathlib import Path

import pytest

from shorts.config import (
    Config, IdeateCfg, RenderCfg, SubtitleCfg, TranscribeCfg, VoiceCfg,
)
from shorts.project import Manifest, Project
from shorts.web.app import create_app


def _config(tmp_path: Path) -> Config:
    (tmp_path / "assets").mkdir()
    return Config(
        root=tmp_path,
        projects_dir=tmp_path / "projects",
        assets_dir=tmp_path / "assets",
        aspect="9:16",
        transcribe=TranscribeCfg(model="whisper-1"),
        ideate=IdeateCfg(model="gpt-4.1", count=6),
        voice=VoiceCfg(model="m", voice="alloy", instructions=None, speed=None),
        render=RenderCfg(
            min_beat_duration=3.0,
            subtitle=SubtitleCfg(
                enabled=True, font=None, font_size=None, primary_color=None,
                bold=False, italic=False, uppercase=False, position=None,
                margin_vertical=None, max_chars_per_line=None, max_lines=None,
                max_duration=None,
            ),
        ),
        openai_api_key="sk-test",
    )


def _idea_md(slug, narration, approved=False):
    box = "x" if approved else " "
    return (
        f"---\nslug: {slug}\ntitle: Demo Idea\n---\n\n"
        f"- [{box}] Approved\n\n## Hook\n\nh\n\n"
        f"## Narration\n\n{narration}\n\n## Notes\n\nn\n"
    )


@pytest.fixture
def client(tmp_path):
    cfg = _config(tmp_path)
    project = Project.create(cfg.projects_dir, "demo")
    Manifest.new("demo").save(project.manifest_path)
    project.idea_file("01-x").write_text(_idea_md("01-x", "the script", approved=True))
    app = create_app(cfg)
    app.config.update(TESTING=True)
    return app.test_client(), cfg, project


def test_get_projects_lists_demo(client):
    c, _, _ = client
    rows = c.get("/api/projects").get_json()
    assert [r["name"] for r in rows] == ["demo"]
    assert "fetch" in rows[0]["stages"]


def test_get_project_snapshot(client):
    c, _, _ = client
    snap = c.get("/api/projects/demo").get_json()
    assert snap["name"] == "demo"
    assert [s["stage"] for s in snap["stages"]] == [
        "fetch", "transcribe", "ideate", "voice", "plan", "render",
    ]
    assert snap["ideas"][0]["slug"] == "01-x"
    assert snap["ideas"][0]["approved"] is True
    assert snap["job"] is None


def test_get_unknown_project_404(client):
    c, _, _ = client
    resp = c.get("/api/projects/nope")
    assert resp.status_code == 404
    assert "error" in resp.get_json()


def test_get_jobs_current_idle(client):
    c, _, _ = client
    assert c.get("/api/jobs/current").get_json()["running"] is False


def test_index_served(client):
    c, _, _ = client
    resp = c.get("/")
    assert resp.status_code == 200
    assert b"<" in resp.data


def test_put_prompt_writes_file(client):
    c, _, project = client
    resp = c.put("/api/projects/demo/prompt", json={"prompt": "novo brief pt-br"})
    assert resp.status_code == 200
    assert json.loads(project.prompt_path.read_text()) == {"prompt": "novo brief pt-br"}
    assert resp.get_json()["prompt"] == "novo brief pt-br"


def test_put_prompt_empty_422(client):
    c, _, _ = client
    resp = c.put("/api/projects/demo/prompt", json={"prompt": "  "})
    assert resp.status_code == 422


def test_put_idea_updates_md(client):
    c, _, project = client
    resp = c.put(
        "/api/projects/demo/ideas/01-x",
        json={"narration": "rewritten narration", "approved": False},
    )
    assert resp.status_code == 200
    md = project.idea_file("01-x").read_text()
    assert "rewritten narration" in md
    assert "- [ ] Approved" in md
    assert "## Notes\n\nn" in md


def test_put_idea_unknown_slug_404(client):
    c, _, _ = client
    resp = c.put(
        "/api/projects/demo/ideas/99-nope",
        json={"narration": "x", "approved": False},
    )
    assert resp.status_code == 404


def test_put_plan_valid_and_invalid(client):
    c, _, project = client
    ok = c.put(
        "/api/projects/demo/ideas/01-x/plan",
        json={"plan": '{"audio_path":"a.mp3","beats":[{"start":0,"end":1}]}'},
    )
    assert ok.status_code == 200
    assert json.loads(project.plan_file("01-x").read_text())["beats"][0]["end"] == 1

    bad = c.put("/api/projects/demo/ideas/01-x/plan", json={"plan": "{bad"})
    assert bad.status_code == 422
