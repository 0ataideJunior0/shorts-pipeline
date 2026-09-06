from shorts.ideas import sync_idea_state
from shorts.project import Manifest, Project, sha256_text


def _make_idea(project: Project, name: str, *, approved: bool, narration: str) -> None:
    box = "x" if approved else " "
    project.idea_file(name).write_text(
        f"---\nslug: {name}\n---\n\n- [{box}] Approved\n\n"
        f"## Narration\n\n{narration}\n\n## Notes\n\nx\n"
    )


def test_sync_records_approval_and_hash(tmp_path):
    project = Project.create(tmp_path, "demo")
    _make_idea(project, "01-a", approved=True, narration="hello world")
    _make_idea(project, "02-b", approved=False, narration="second one")

    manifest = Manifest.new("demo")
    result = sync_idea_state(project, manifest)

    assert [slug for slug, _ in result] == ["01-a", "02-b"]
    assert manifest.get_idea("01-a") == {
        "approved": True,
        "script_sha256": sha256_text("hello world"),
    }
    assert manifest.get_idea("02-b")["approved"] is False


def test_sync_updates_hash_when_narration_edited(tmp_path):
    project = Project.create(tmp_path, "demo")
    _make_idea(project, "01-a", approved=True, narration="original")
    manifest = Manifest.new("demo")
    sync_idea_state(project, manifest)

    _make_idea(project, "01-a", approved=True, narration="edited text")
    sync_idea_state(project, manifest)
    assert manifest.get_idea("01-a")["script_sha256"] == sha256_text("edited text")


def test_sync_falls_back_to_file_stem(tmp_path):
    project = Project.create(tmp_path, "demo")
    project.idea_file("07-no-fm").write_text(
        "- [ ] Approved\n\n## Narration\n\nbody\n"
    )
    manifest = Manifest.new("demo")
    result = sync_idea_state(project, manifest)
    assert result[0][0] == "07-no-fm"
    assert "07-no-fm" in manifest.ideas
