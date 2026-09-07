import json

from shorts.config import (
    Config, IdeateCfg, RenderCfg, SubtitleCfg, TranscribeCfg, VoiceCfg,
)
from shorts.project import Manifest, Project, sha256_text
from shorts.web.state import (
    build_snapshot, idea_freshness, list_projects, prompt_text, stage_rows,
)


def _config(tmp_path):
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
        f"---\nslug: {slug}\ntitle: T\n---\n\n"
        f"- [{box}] Approved\n\n## Hook\n\nh\n\n"
        f"## Narration\n\n{narration}\n\n## Notes\n\nn\n"
    )


def _project(tmp_path, name="demo"):
    cfg = _config(tmp_path)
    project = Project.create(cfg.projects_dir, name)
    Manifest.new(name).save(project.manifest_path)
    return cfg, project


def test_stage_rows_fresh_project_only_fetch_ready(tmp_path):
    cfg, project = _project(tmp_path)
    rows = stage_rows(project, Manifest.load(project.manifest_path), cfg)
    by = {r["stage"]: r for r in rows}
    assert [r["stage"] for r in rows] == [
        "fetch", "transcribe", "ideate", "voice", "plan", "render",
    ]
    assert by["fetch"]["status"] == "ready"
    assert by["transcribe"]["status"] == "blocked"
    assert by["render"]["status"] == "blocked"


def test_stage_rows_after_fetch_and_transcribe(tmp_path):
    cfg, project = _project(tmp_path)
    project.video_path.write_bytes(b"x")
    project.transcript_txt_path.write_text("hello")
    m = Manifest.load(project.manifest_path)
    m.stage_done("fetch")
    m.stage_done("transcribe", audio_sha256="none", outputs=[])
    m.save(project.manifest_path)
    by = {r["stage"]: r for r in stage_rows(project, m, cfg)}
    assert by["fetch"]["status"] == "done"
    assert by["transcribe"]["status"] == "done"
    assert by["ideate"]["status"] == "ready"


def test_idea_freshness_missing_then_fresh(tmp_path):
    cfg, project = _project(tmp_path)
    narration = "the script"
    project.idea_file("01-x").write_text(_idea_md("01-x", narration, approved=True))
    m = Manifest.load(project.manifest_path)
    from shorts.ideas import sync_idea_state
    sync_idea_state(project, m)
    fr = idea_freshness(project, "01-x", m, opts_hash="deadbeef")
    assert fr == {"voice": "missing", "plan": "missing", "render": "missing"}

    project.voice_file("01-x").parent.mkdir(parents=True, exist_ok=True)
    project.voice_file("01-x").write_bytes(b"mp3")
    m.set_idea("01-x", voice={
        "path": "voice/01-x.mp3",
        "script_sha256": sha256_text(narration),
        "params_sha256": "vp",
    })
    fr = idea_freshness(project, "01-x", m, opts_hash="deadbeef")
    assert fr["voice"] == "fresh"


def test_build_snapshot_shape(tmp_path):
    cfg, project = _project(tmp_path)
    project.idea_file("01-x").write_text(_idea_md("01-x", "script one", approved=True))
    project.prompt_path.write_text(json.dumps({"prompt": "meu brief"}) + "\n")
    snap = build_snapshot(project, cfg)
    assert snap["name"] == "demo"
    assert snap["prompt"] == "meu brief"
    assert snap["job"] is None
    assert [s["stage"] for s in snap["stages"]] == [
        "fetch", "transcribe", "ideate", "voice", "plan", "render",
    ]
    assert snap["ideas"][0]["slug"] == "01-x"
    assert snap["ideas"][0]["approved"] is True
    assert snap["ideas"][0]["narration"] == "script one"
    assert snap["ideas"][0]["voice"] == "missing"


def test_prompt_text_fallbacks(tmp_path):
    cfg, project = _project(tmp_path)
    from shorts.prompt import DEFAULT_IDEATE_PROMPT
    assert prompt_text(project) == DEFAULT_IDEATE_PROMPT
    project.prompt_path.write_text("{ broken")
    assert prompt_text(project) == "{ broken"


def test_list_projects(tmp_path):
    cfg, project = _project(tmp_path, "demo")
    rows = list_projects(cfg)
    assert rows[0]["name"] == "demo"
    assert "fetch" in rows[0]["stages"]
