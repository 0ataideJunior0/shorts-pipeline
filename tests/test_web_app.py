import json
from pathlib import Path

import pytest

from shorts.config import (
    Config, IdeateCfg, RenderCfg, SubtitleCfg, TranscribeCfg, VoiceCfg, YouTubeCfg,
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
        voice=VoiceCfg(model="m", voice="Kore", instructions=None),
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
        google_api_key="gm-test",
        youtube=YouTubeCfg(client_secret=None,
                           token_path=tmp_path / ".youtube_token.json",
                           category_id=22),
    )


def _idea_md(slug, narration, approved=False):
    box = "x" if approved else " "
    return (
        f"---\nslug: {slug}\ntitle: Demo Idea\n---\n\n"
        f"- [{box}] Approved\n\n## Description\n\nold caption\n\n"
        f"## Tags\n\nold, tags\n\n## Hook\n\nh\n\n"
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


def test_corrupt_manifest_is_422_and_does_not_500_the_list(client):
    c, cfg, _ = client
    broken = cfg.projects_dir / "broken"
    broken.mkdir()
    (broken / "manifest.json").write_text("{ truncated")

    detail = c.get("/api/projects/broken")
    assert detail.status_code == 422
    assert "manifest.json" in detail.get_json()["error"]

    listing = c.get("/api/projects")
    assert listing.status_code == 200
    names = [r["name"] for r in listing.get_json()]
    assert "demo" in names and "broken" not in names


def test_get_jobs_current_idle(client):
    c, _, _ = client
    assert c.get("/api/jobs/current").get_json()["running"] is False


def test_index_served(client):
    c, _, _ = client
    resp = c.get("/")
    assert resp.status_code == 200
    assert b"EventSource" in resp.data


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
        json={
            "title": "Renamed short",
            "description": "A punchier caption.",
            "tags": "gta 6, rockstar, leonida",
            "narration": "rewritten narration",
            "approved": False,
        },
    )
    assert resp.status_code == 200
    md = project.idea_file("01-x").read_text()
    assert "title: Renamed short\n" in md
    assert "## Description\n\nA punchier caption.\n" in md
    assert "## Tags\n\ngta 6, rockstar, leonida\n" in md
    assert "rewritten narration" in md
    assert "- [ ] Approved" in md
    assert "## Notes\n\nn" in md
    idea = resp.get_json()["ideas"][0]
    assert idea["title"] == "Renamed short"
    assert idea["description"] == "A punchier caption."
    assert idea["tags"] == "gta 6, rockstar, leonida"


def test_put_approved_toggles_only_the_checkbox(client):
    c, _, project = client
    before = project.idea_file("01-x").read_text()
    assert "- [x] Approved" in before
    resp = c.put("/api/projects/demo/ideas/01-x/approved", json={"approved": False})
    assert resp.status_code == 200
    md = project.idea_file("01-x").read_text()
    assert "- [ ] Approved" in md
    assert "the script" in md  # narration untouched
    assert "title: Demo Idea" in md
    assert resp.get_json()["ideas"][0]["approved"] is False


def test_put_approved_unknown_idea_404(client):
    c, _, _ = client
    assert c.put("/api/projects/demo/ideas/99-nope/approved",
                 json={"approved": True}).status_code == 404


def test_voice_route_serves_and_404s(client):
    c, _, project = client
    assert c.get("/api/projects/demo/voice/01-x").status_code == 404
    project.voice_file("01-x").write_bytes(b"ID3fake-mp3-bytes")
    resp = c.get("/api/projects/demo/voice/01-x")
    assert resp.status_code == 200
    assert resp.mimetype == "audio/mpeg"
    assert resp.data == b"ID3fake-mp3-bytes"


def test_categories_route(client):
    c, cfg, project = client
    (cfg.assets_dir / "neon").mkdir()
    (cfg.assets_dir / "neon" / "a.mp4").write_bytes(b"x")
    (cfg.assets_dir / "neon" / "b.mp4").write_bytes(b"x")
    project.plan_file("01-x").write_text(json.dumps({
        "beats": [{"category": "neon", "description": "neon skyline"},
                  {"category": "swamp", "description": "misty swamp"}]
    }))
    rows = c.get("/api/projects/demo/categories").get_json()
    by = {r["category"]: r for r in rows}
    assert by["neon"]["assets"] == 2
    assert by["neon"]["beats"] == ["neon skyline"]
    assert by["swamp"]["assets"] == 0  # referenced by a beat, no folder
    # categories a plan needs come before folder-only ones
    assert [r["category"] for r in rows][:2] == ["neon", "swamp"]


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


class _FakeRunner:
    def __init__(self):
        self.started = []
        self.busy = False
        self._q = None

    def running(self):
        return self.busy

    def state(self):
        return {"running": self.busy, "stage": "fetch" if self.busy else None,
                "project": "demo" if self.busy else None,
                "started_at": None, "returncode": None, "finished_at": None}

    def start(self, stage, project, cmd):
        from shorts.web.jobs import JobBusy
        if self.busy:
            raise JobBusy("busy")
        self.started.append((stage, project, cmd))
        self.busy = True

    def cancel(self):
        from shorts.web.jobs import JobBusy
        if not self.busy:
            raise JobBusy("idle")
        self.busy = False

    def attach(self):
        import queue
        q = queue.Queue()
        q.put({"type": "line", "text": "hello from stream"})
        q.put(None)
        return q

    def detach(self, q):
        pass


@pytest.fixture
def fake_client(tmp_path):
    cfg = _config(tmp_path)
    Project.create(cfg.projects_dir, "demo")
    Manifest.new("demo").save((cfg.projects_dir / "demo" / "manifest.json"))
    app = create_app(cfg)
    fake = _FakeRunner()
    app.config["JOB_RUNNER"] = fake
    return app.test_client(), fake


def test_post_run_stage_builds_argv(fake_client):
    c, fake = fake_client
    resp = c.post("/api/projects/demo/run/ideate", json={"force": True})
    assert resp.status_code == 202
    stage, project, cmd = fake.started[0]
    assert stage == "ideate" and project == "demo"
    assert cmd[-3:] == ["ideate", "demo", "--force"]
    assert cmd[1:3] == ["-m", "shorts"]


def test_post_run_bad_stage_400(fake_client):
    c, _ = fake_client
    assert c.post("/api/projects/demo/run/fetch").status_code == 400
    assert c.post("/api/projects/demo/run/bogus").status_code == 400


def test_post_run_busy_409(fake_client):
    c, fake = fake_client
    fake.busy = True
    assert c.post("/api/projects/demo/run/voice").status_code == 409


def test_post_projects_requires_url_and_name(fake_client):
    c, _ = fake_client
    assert c.post("/api/projects", json={"url": "http://x"}).status_code == 400
    assert c.post("/api/projects", json={"name": "y"}).status_code == 400


def test_post_projects_starts_fetch(fake_client):
    c, fake = fake_client
    resp = c.post("/api/projects", json={"url": "http://x", "name": "New Clip"})
    assert resp.status_code == 202
    stage, project, cmd = fake.started[0]
    assert stage == "fetch" and project == "new-clip"
    assert cmd[-4:] == ["fetch", "http://x", "--name", "new-clip"]


def test_stream_returns_buffered_event(fake_client):
    c, _ = fake_client
    resp = c.get("/api/jobs/current/stream")
    assert resp.status_code == 200
    assert resp.mimetype == "text/event-stream"
    body = resp.get_data(as_text=True)
    assert 'data: {"type": "line", "text": "hello from stream"}' in body


def test_cancel_idle_409(fake_client):
    c, _ = fake_client
    assert c.post("/api/jobs/current/cancel").status_code == 409


def test_youtube_status_not_configured(client):
    c, _, _ = client
    body = c.get("/api/youtube/status").get_json()
    assert body == {"connected": False, "channel": None, "error": "not configured"}


def test_youtube_status_connected(client, monkeypatch):
    c, cfg, _ = client
    (cfg.youtube.token_path).write_text("{}")  # file exists → not "not configured"
    import shorts.youtube as yt
    monkeypatch.setattr(yt, "get_credentials", lambda c: object())
    monkeypatch.setattr(yt, "channel_title", lambda c: "My Channel")
    body = c.get("/api/youtube/status").get_json()
    assert body == {"connected": True, "channel": "My Channel", "error": None}


def test_youtube_status_expired(client, monkeypatch):
    c, cfg, _ = client
    (cfg.youtube.token_path).write_text("{}")
    import shorts.youtube as yt
    monkeypatch.setattr(yt, "get_credentials",
        lambda c: (_ for _ in ()).throw(yt.YouTubeAuthError("x", reason="expired")))
    assert c.get("/api/youtube/status").get_json()["error"] == "token expired"


def test_put_cadence_and_queue(client):
    c, _, project = client
    r = c.put("/api/projects/demo/publish/cadence",
              json={"start": "2026-09-14T09:00:00Z", "interval_hours": 24, "weekdays": [1, 2, 3, 4, 5]})
    assert r.status_code == 200
    from shorts.project import Manifest
    assert Manifest.load(project.manifest_path).get_publish()["interval_hours"] == 24
    assert r.get_json()["cadence"]["weekdays"] == [1, 2, 3, 4, 5]

    r2 = c.put("/api/projects/demo/publish/cadence", json={"start": None})
    assert Manifest.load(project.manifest_path).get_publish() == {}


def test_put_cadence_bad_start_422(client):
    c, _, _ = client
    assert c.put("/api/projects/demo/publish/cadence",
                 json={"start": "not-a-date"}).status_code == 422


def test_put_cadence_weekdays_scalar_is_422_not_500(client):
    c, _, _ = client
    r = c.put("/api/projects/demo/publish/cadence",
              json={"start": "2026-09-14T09:00:00Z", "weekdays": 5})
    assert r.status_code == 422


def test_put_cadence_weekdays_bool_is_422(client):
    c, _, _ = client
    r = c.put("/api/projects/demo/publish/cadence",
              json={"start": "2026-09-14T09:00:00Z", "weekdays": [True]})
    assert r.status_code == 422


def test_put_cadence_with_daily_times(client):
    c, _, project = client
    r = c.put(
        "/api/projects/demo/publish/cadence",
        json={
            "start": "2026-09-20T10:00:00Z",
            "times": ["10:00", "14:00", "19:00"],
            "weekdays": [1, 2, 3],
        },
    )
    assert r.status_code == 200
    from shorts.project import Manifest
    assert Manifest.load(project.manifest_path).get_publish()["times"] == ["10:00", "14:00", "19:00"]
    body = r.get_json()
    assert body["cadence"]["times"] == ["10:00", "14:00", "19:00"]
    assert body["cadence"]["weekdays"] == [1, 2, 3]

    r2 = c.put(
        "/api/projects/demo/publish/cadence",
        json={"start": "2026-09-20T10:00:00Z", "interval_hours": 12},
    )
    assert r2.status_code == 200
    assert "times" not in Manifest.load(project.manifest_path).get_publish()
    assert "times" not in (r2.get_json()["cadence"] or {})


def test_put_cadence_invalid_times(client):
    c, _, _ = client
    start = "2026-09-20T10:00:00Z"
    for bad in ["10:00", 123, ["99:99"], ["invalid"], [123], ["10:00", "bad"]]:
        r = c.put("/api/projects/demo/publish/cadence", json={"start": start, "times": bad})
        assert r.status_code == 422
        assert r.get_json()["error"] == "times must be a list of HH:MM strings"


def test_put_publish_at(client):
    c, _, project = client
    r = c.put("/api/projects/demo/ideas/01-x/publish-at", json={"publish_at": "2026-10-01T12:00:00Z"})
    assert r.status_code == 200
    from shorts.project import Manifest
    assert Manifest.load(project.manifest_path).get_idea("01-x")["publish_at"] == "2026-10-01T12:00:00Z"
    c.put("/api/projects/demo/ideas/01-x/publish-at", json={"publish_at": None})
    assert "publish_at" not in Manifest.load(project.manifest_path).get_idea("01-x")


def test_post_publish_builds_argv(fake_client):
    c, fake = fake_client
    assert c.post("/api/projects/demo/publish").status_code == 202
    stage, project, cmd = fake.started[-1]
    assert stage == "publish" and cmd[-1] == "demo" and cmd[1:3] == ["-m", "shorts"]
    fake.busy = False  # _FakeRunner does not auto-clear after a start
    c.post("/api/projects/demo/ideas/01-x/publish")
    _s, _p, cmd2 = fake.started[-1]
    assert cmd2[-3:] == ["demo", "--slug", "01-x"]


def test_post_youtube_auth_builds_argv(fake_client):
    c, fake = fake_client
    assert c.post("/api/youtube/auth").status_code == 202
    stage, _project, cmd = fake.started[-1]
    assert stage == "youtube-auth" and cmd[-2:] == ["youtube", "auth"]
