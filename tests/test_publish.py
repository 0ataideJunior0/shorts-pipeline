from datetime import datetime, timedelta, timezone

import pytest

from shorts.publish import (
    build_video_body, cadence_from_manifest, iso, parse_iso, resolve_schedule,
)

UTC = timezone.utc


def test_parse_iso_and_iso_roundtrip():
    dt = parse_iso("2026-09-10T09:00:00Z")
    assert dt == datetime(2026, 9, 10, 9, 0, tzinfo=UTC)
    assert iso(dt) == "2026-09-10T09:00:00Z"


def test_cadence_from_manifest():
    assert cadence_from_manifest({}) is None
    assert cadence_from_manifest({"interval_hours": 24}) is None
    c = cadence_from_manifest({"start": "2026-09-10T09:00:00Z"})
    assert c == {"start": datetime(2026, 9, 10, 9, 0, tzinfo=UTC),
                 "interval_hours": 24, "weekdays": None}


def test_build_video_body_no_schedule():
    body = build_video_body(
        title="T" * 130, description="d", tags=" a, b ,, c ",
        category_id=22, publish_at=None,
    )
    assert len(body["snippet"]["title"]) == 100
    assert body["snippet"]["tags"] == ["a", "b", "c"]
    assert body["snippet"]["categoryId"] == "22"
    assert body["status"] == {"privacyStatus": "private", "selfDeclaredMadeForKids": False}
    assert "publishAt" not in body["status"]


def test_build_video_body_with_schedule():
    body = build_video_body(
        title="t", description="d", tags="", category_id=20,
        publish_at=datetime(2026, 9, 11, 12, 30, tzinfo=UTC),
    )
    assert body["snippet"]["tags"] == []
    assert body["status"]["publishAt"] == "2026-09-11T12:30:00Z"


def test_resolve_schedule_override_beats_cadence():
    ov = datetime(2026, 9, 20, 8, 0, tzinfo=UTC)
    cad = {"start": datetime(2026, 9, 10, 9, 0, tzinfo=UTC),
           "interval_hours": 24, "weekdays": None}
    out = resolve_schedule(["a", "b"], {"a": ov}, cad, set())
    assert out["a"] == ov
    assert out["b"] == datetime(2026, 9, 10, 9, 0, tzinfo=UTC)


def test_resolve_schedule_sequential_slots_and_taken():
    start = datetime(2026, 9, 10, 9, 0, tzinfo=UTC)
    cad = {"start": start, "interval_hours": 24, "weekdays": None}
    taken = {start + timedelta(days=1)}  # slot k=1 already used
    out = resolve_schedule(["a", "b"], {}, cad, taken)
    assert out["a"] == start
    assert out["b"] == start + timedelta(days=2)  # k=1 skipped


def test_resolve_schedule_weekday_filter_skips():
    # 2026-09-12 is a Saturday (isoweekday 6); allow Mon-Fri only
    start = datetime(2026, 9, 12, 9, 0, tzinfo=UTC)
    cad = {"start": start, "interval_hours": 24, "weekdays": [1, 2, 3, 4, 5]}
    out = resolve_schedule(["a"], {}, cad, set())
    assert out["a"] == datetime(2026, 9, 14, 9, 0, tzinfo=UTC)  # Monday


def test_resolve_schedule_none_without_cadence():
    assert resolve_schedule(["a"], {}, None, set()) == {"a": None}


def test_resolve_schedule_impossible_filter_hits_cap():
    cad = {"start": datetime(2026, 9, 10, 9, 0, tzinfo=UTC),
           "interval_hours": 24, "weekdays": []}
    assert resolve_schedule(["a"], {}, cad, set()) == {"a": None}


import json as _json

from shorts.project import Manifest, Project


def _mk_project(tmp_path, cfg):
    project = Project.create(cfg.projects_dir, "demo")
    Manifest.new("demo").save(project.manifest_path)
    return project


def _cfg(tmp_path):
    from shorts.config import (
        Config, IdeateCfg, RenderCfg, SubtitleCfg, TranscribeCfg, VoiceCfg, YouTubeCfg,
    )
    (tmp_path / "assets").mkdir()
    return Config(
        root=tmp_path, projects_dir=tmp_path / "projects", assets_dir=tmp_path / "assets",
        aspect="9:16",
        transcribe=TranscribeCfg(model="w"), ideate=IdeateCfg(model="g", count=6),
        voice=VoiceCfg(model="m", voice="alloy", instructions=None, speed=None),
        render=RenderCfg(min_beat_duration=3.0, subtitle=SubtitleCfg(
            enabled=True, font=None, font_size=None, primary_color=None, bold=False,
            italic=False, uppercase=False, position=None, margin_vertical=None,
            max_chars_per_line=None, max_lines=None, max_duration=None)),
        openai_api_key="sk", youtube=YouTubeCfg(
            client_secret=None, token_path=tmp_path / ".youtube_token.json",
            category_id=22),
    )


IDEA_MD = (
    "---\nslug: {s}\ntitle: {t}\n---\n\n- [x] Approved\n\n"
    "## Description\n\ndesc {s}\n\n## Tags\n\ntag one, tag two\n\n"
    "## Hook\n\nh\n\n## Narration\n\nn {s}\n\n## Notes\n\nx\n"
)


def _fresh_rendered_idea(project, slug, title="T"):
    project.idea_file(slug).write_text(IDEA_MD.format(s=slug, t=title))
    project.render_file(slug).parent.mkdir(parents=True, exist_ok=True)
    project.render_file(slug).write_bytes(b"mp4")
    project.plan_file(slug).write_text('{"beats": []}')
    from shorts.project import sha256_file
    m = Manifest.load(project.manifest_path)
    m.set_idea(slug, approved=True, script_sha256="s",
               voice={"path": f"voice/{slug}.mp3", "script_sha256": "s", "params_sha256": "vp"},
               plan={"path": f"renders/{slug}.plan.json", "script_sha256": "s",
                     "voice_params_sha256": "vp", "opts_sha256": _opts(m, project)},
               render={"path": f"renders/{slug}.mp4",
                       "plan_sha256": sha256_file(project.plan_file(slug))})
    m.save(project.manifest_path)


def _opts(_m, _p):
    # opts_sha256 doesn't affect render freshness; any stable value works here
    return "x"


def test_run_uploads_eligible_and_records(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    project = _mk_project(tmp_path, cfg)
    _fresh_rendered_idea(project, "01-x", "First")
    _fresh_rendered_idea(project, "02-y", "Second")

    import shorts.publish as pub
    monkeypatch.setattr(pub, "get_credentials", lambda c: object())
    monkeypatch.setattr(pub, "youtube_service", lambda c: object())
    seen = []
    def fake_insert(service, *, mp4_path, body):
        seen.append((mp4_path.name, body["snippet"]["title"], body["status"].get("publishAt")))
        return {"video_id": f"v{len(seen)}", "url": f"https://youtu.be/v{len(seen)}"}
    monkeypatch.setattr(pub, "insert_video", fake_insert)

    m = Manifest.load(project.manifest_path)
    m.set_publish(start="2026-09-14T09:00:00Z", interval_hours=24, weekdays=None)
    m.save(project.manifest_path)

    pub.run(project, cfg)

    assert [s[0] for s in seen] == ["01-x.mp4", "02-y.mp4"]
    assert seen[0][2] == "2026-09-14T09:00:00Z"
    assert seen[1][2] == "2026-09-15T09:00:00Z"
    back = Manifest.load(project.manifest_path)
    assert back.get_idea("01-x")["youtube"]["video_id"] == "v1"
    assert back.get_idea("01-x")["youtube"]["privacy"] == "private"


def test_run_skips_already_uploaded_unless_force(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    project = _mk_project(tmp_path, cfg)
    _fresh_rendered_idea(project, "01-x")
    m = Manifest.load(project.manifest_path)
    m.set_idea("01-x", youtube={"video_id": "old", "url": "u", "publish_at": None})
    m.save(project.manifest_path)

    import shorts.publish as pub
    monkeypatch.setattr(pub, "get_credentials", lambda c: object())
    monkeypatch.setattr(pub, "youtube_service", lambda c: object())
    calls = []
    monkeypatch.setattr(pub, "insert_video",
                        lambda *a, **k: calls.append(1) or {"video_id": "new", "url": "u2"})

    pub.run(project, cfg)                 # skipped
    assert calls == []
    pub.run(project, cfg, force=True)     # re-uploaded
    assert calls == [1]


def test_run_propagates_auth_error(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    project = _mk_project(tmp_path, cfg)
    _fresh_rendered_idea(project, "01-x")
    import shorts.publish as pub
    from shorts.youtube import YouTubeAuthError
    def boom(_c): raise YouTubeAuthError("expired", reason="expired")
    monkeypatch.setattr(pub, "get_credentials", boom)
    with pytest.raises(YouTubeAuthError):
        pub.run(project, cfg)


def test_run_isolates_per_idea_failure(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    project = _mk_project(tmp_path, cfg)
    _fresh_rendered_idea(project, "01-x")
    _fresh_rendered_idea(project, "02-y")
    import shorts.publish as pub
    monkeypatch.setattr(pub, "get_credentials", lambda c: object())
    monkeypatch.setattr(pub, "youtube_service", lambda c: object())

    class Err(Exception):
        def __init__(self): self.resp = type("R", (), {"status": 400})(); self.content = b'{"error":{"message":"bad"}}'
    monkeypatch.setattr(pub, "HttpError", Err, raising=False)

    def flaky(service, *, mp4_path, body):
        if mp4_path.name == "01-x.mp4":
            raise Err()
        return {"video_id": "v2", "url": "https://youtu.be/v2"}
    monkeypatch.setattr(pub, "insert_video", flaky)

    with pytest.raises(SystemExit):
        pub.run(project, cfg)
    back = Manifest.load(project.manifest_path)
    assert "youtube" not in back.get_idea("01-x")
    assert back.get_idea("02-y")["youtube"]["video_id"] == "v2"
