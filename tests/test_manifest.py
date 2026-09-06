import hashlib

from shorts.project import Manifest, sha256_file, sha256_text, utcnow_iso


def test_sha256_helpers(tmp_path):
    assert sha256_text("hello") == hashlib.sha256(b"hello").hexdigest()
    f = tmp_path / "a.bin"
    f.write_bytes(b"hello")
    assert sha256_file(f) == hashlib.sha256(b"hello").hexdigest()


def test_utcnow_iso_format():
    value = utcnow_iso()
    assert value.endswith("Z")
    assert "T" in value
    assert "." not in value


def test_new_save_load_roundtrip(tmp_path):
    m = Manifest.new("demo")
    m.source = {"url": "u", "video_id": "v", "title": "t"}
    m.stage_done("fetch", outputs=["source/video.mp4"])
    path = tmp_path / "manifest.json"
    m.save(path)

    assert not (tmp_path / "manifest.json.tmp").exists()
    loaded = Manifest.load(path)
    assert loaded.name == "demo"
    assert loaded.source["title"] == "t"
    assert loaded.stages["fetch"]["status"] == "done"
    assert loaded.stages["fetch"]["outputs"] == ["source/video.mp4"]
    assert loaded.stages["fetch"]["at"].endswith("Z")


def test_stage_and_idea_merge():
    m = Manifest.new("demo")
    assert m.get_stage("ideate") is None
    assert m.is_stage_done("ideate") is False

    m.stage_done("ideate", model="gpt-4.1")
    m.stage_done("ideate", transcript_sha256="abc")
    assert m.is_stage_done("ideate") is True
    assert m.stages["ideate"]["model"] == "gpt-4.1"
    assert m.stages["ideate"]["transcript_sha256"] == "abc"

    assert m.get_idea("01-x") == {}
    m.set_idea("01-x", approved=False)
    m.set_idea("01-x", script_sha256="h1")
    m.set_idea("01-x", approved=True)
    assert m.get_idea("01-x") == {"approved": True, "script_sha256": "h1"}
