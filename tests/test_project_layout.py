import pytest

from shorts.project import Project, slugify


def test_slugify():
    assert slugify("X — My Morning Routine!") == "x-my-morning-routine"
    assert slugify("  多 spaces  ") == "spaces"
    assert slugify("!!!") == "untitled"
    assert slugify("already-good") == "already-good"


def test_paths(tmp_path):
    p = Project(name="demo", root=tmp_path / "demo")
    assert p.manifest_path == tmp_path / "demo" / "manifest.json"
    assert p.video_path == tmp_path / "demo" / "source" / "video.mp4"
    assert p.audio_path == tmp_path / "demo" / "audio" / "source.mp3"
    assert p.transcript_txt_path == tmp_path / "demo" / "transcript" / "transcript.txt"
    assert p.prompt_path == tmp_path / "demo" / "ideas" / "prompt.json"
    assert p.idea_file("01-foo") == tmp_path / "demo" / "ideas" / "01-foo.md"
    assert p.voice_file("01-foo") == tmp_path / "demo" / "voice" / "01-foo.mp3"
    assert p.render_file("01-foo") == tmp_path / "demo" / "renders" / "01-foo.mp4"
    assert p.plan_file("01-foo") == tmp_path / "demo" / "renders" / "01-foo.plan.json"


def test_create_and_load(tmp_path):
    p = Project.create(tmp_path, "demo")
    assert p.ideas_dir.is_dir()
    assert p.renders_dir.is_dir()
    with pytest.raises(FileExistsError):
        Project.create(tmp_path, "demo")
    loaded = Project.load(tmp_path, "demo")
    assert loaded.root == p.root


def test_load_missing(tmp_path):
    with pytest.raises(FileNotFoundError):
        Project.load(tmp_path, "nope")


def test_discover(tmp_path):
    with pytest.raises(FileNotFoundError):
        Project.discover(tmp_path, None)

    a = Project.create(tmp_path, "a")
    (a.manifest_path).write_text("{}")
    assert Project.discover(tmp_path, None).name == "a"

    b = Project.create(tmp_path, "b")
    (b.manifest_path).write_text("{}")
    import os
    old = a.manifest_path.stat().st_mtime
    os.utime(b.manifest_path, (old + 100, old + 100))
    assert Project.discover(tmp_path, None).name == "b"
    assert Project.discover(tmp_path, "a").name == "a"


def test_list_all_needs_manifest(tmp_path):
    Project.create(tmp_path, "a")  # no manifest written
    (tmp_path / "loose_file").write_text("x")
    assert Project.list_all(tmp_path) == []
    Project.load(tmp_path, "a").manifest_path.write_text("{}")
    assert [p.name for p in Project.list_all(tmp_path)] == ["a"]
