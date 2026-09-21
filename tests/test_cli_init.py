import types
from pathlib import Path
import pytest
from click.testing import CliRunner

import shorts.cli as cli
from shorts.project import Manifest


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def fake_config(monkeypatch, tmp_path):
    projects_dir = tmp_path / "projects"
    projects_dir.mkdir(parents=True, exist_ok=True)
    fake = types.SimpleNamespace(
        projects_dir=projects_dir,
        render=types.SimpleNamespace(
            min_beat_duration=3.0,
            subtitle=types.SimpleNamespace(
                enabled=True, font=None, font_size=None, primary_color=None,
                bold=False, italic=False, uppercase=False, position=None,
                margin_vertical=None, max_chars_per_line=None, max_lines=None,
                max_duration=None,
            ),
        ),
    )
    monkeypatch.setattr(cli, "_config", lambda ctx: fake)
    return fake


def test_init_with_text(runner, fake_config):
    r = runner.invoke(cli.cli, ["init", "my-proj", "--text", "test content"])
    assert r.exit_code == 0
    assert "init: initialized project 'my-proj'" in r.output

    project_dir = fake_config.projects_dir / "my-proj"
    assert project_dir.is_dir()

    # Verify transcript.txt
    transcript_file = project_dir / "transcript" / "transcript.txt"
    assert transcript_file.is_file()
    assert transcript_file.read_text(encoding="utf-8") == "test content"

    # Verify prompt.json
    assert (project_dir / "ideas" / "prompt.json").is_file()

    # Verify manifest
    manifest_file = project_dir / "manifest.json"
    assert manifest_file.is_file()
    manifest = Manifest.load(manifest_file)
    assert manifest.name == "my-proj"
    assert manifest.source == {
        "type": "text",
        "title": "my-proj",
    }
    assert manifest.is_stage_skipped("fetch") is True
    assert manifest.is_stage_skipped("transcribe") is True
    assert manifest.stages["fetch"]["status"] == "skipped"
    assert manifest.stages["transcribe"]["status"] == "skipped"


def test_init_with_txt_file(runner, fake_config, tmp_path):
    sample_file = tmp_path / "sample.txt"
    sample_file.write_text("file content from txt", encoding="utf-8")

    r = runner.invoke(cli.cli, ["init", "my-file-proj", "--file", str(sample_file)])
    assert r.exit_code == 0
    assert "init: initialized project 'my-file-proj'" in r.output

    project_dir = fake_config.projects_dir / "my-file-proj"
    transcript_file = project_dir / "transcript" / "transcript.txt"
    assert transcript_file.read_text(encoding="utf-8") == "file content from txt"

    manifest = Manifest.load(project_dir / "manifest.json")
    assert manifest.source == {
        "type": "file",
        "title": "my-file-proj",
        "file": str(sample_file.resolve()),
    }
    assert manifest.is_stage_skipped("fetch") is True
    assert manifest.is_stage_skipped("transcribe") is True


def test_init_with_md_file(runner, fake_config, tmp_path):
    sample_file = tmp_path / "sample.md"
    sample_file.write_text("# Markdown idea content", encoding="utf-8")

    r = runner.invoke(cli.cli, ["init", "my-md-proj", "--file", str(sample_file)])
    assert r.exit_code == 0
    assert "init: initialized project 'my-md-proj'" in r.output

    project_dir = fake_config.projects_dir / "my-md-proj"
    transcript_file = project_dir / "transcript" / "transcript.txt"
    assert transcript_file.read_text(encoding="utf-8") == "# Markdown idea content"

    manifest = Manifest.load(project_dir / "manifest.json")
    assert manifest.source == {
        "type": "file",
        "title": "my-md-proj",
        "file": str(sample_file.resolve()),
    }
    assert manifest.is_stage_skipped("fetch") is True
    assert manifest.is_stage_skipped("transcribe") is True


def test_init_invalid_extension(runner, fake_config, tmp_path):
    sample_pdf = tmp_path / "sample.pdf"
    sample_pdf.write_bytes(b"%PDF-1.4...")

    r = runner.invoke(cli.cli, ["init", "invalid", "--file", str(sample_pdf)])
    assert r.exit_code != 0
    assert "Only .txt and .md files are supported." in r.output

    r2 = runner.invoke(cli.cli, ["init", "invalid2", "--file", "nonexistent.pdf"])
    assert r2.exit_code != 0
    assert "Only .txt and .md files are supported." in r2.output


def test_init_missing_file(runner, fake_config, tmp_path):
    nonexistent = tmp_path / "nonexistent.txt"
    r = runner.invoke(cli.cli, ["init", "missing-file", "--file", str(nonexistent)])
    assert r.exit_code != 0
    assert f"File not found: {nonexistent}" in r.output


def test_init_no_input(runner, fake_config):
    r = runner.invoke(cli.cli, ["init", "no-input"])
    assert r.exit_code != 0
    assert "Provide either --text or --file, but not both." in r.output


def test_init_both_inputs(runner, fake_config, tmp_path):
    sample_file = tmp_path / "sample.txt"
    sample_file.write_text("abc", encoding="utf-8")

    r = runner.invoke(cli.cli, ["init", "both-inputs", "--text", "abc", "--file", str(sample_file)])
    assert r.exit_code != 0
    assert "Provide either --text or --file, but not both." in r.output


def test_init_existing_project_force(runner, fake_config):
    r = runner.invoke(cli.cli, ["init", "existing-proj", "--text", "initial content"])
    assert r.exit_code == 0

    # Without --force
    r_fail = runner.invoke(cli.cli, ["init", "existing-proj", "--text", "new content"])
    assert r_fail.exit_code != 0
    assert "Project 'existing-proj' already exists. Use --force to overwrite." in r_fail.output

    # With --force
    r_force = runner.invoke(cli.cli, ["init", "existing-proj", "--text", "new content", "--force"])
    assert r_force.exit_code == 0
    transcript_file = fake_config.projects_dir / "existing-proj" / "transcript" / "transcript.txt"
    assert transcript_file.read_text(encoding="utf-8") == "new content"


def test_init_slugification_and_title(runner, fake_config):
    r = runner.invoke(cli.cli, ["init", "My Cool Project!", "--text", "content"])
    assert r.exit_code == 0
    assert "init: initialized project 'my-cool-project'" in r.output

    project_dir = fake_config.projects_dir / "my-cool-project"
    assert project_dir.is_dir()
    manifest = Manifest.load(project_dir / "manifest.json")
    assert manifest.name == "my-cool-project"
    assert manifest.source["title"] == "My Cool Project!"


def test_init_case_insensitive_extension(runner, fake_config, tmp_path):
    sample_txt = tmp_path / "SAMPLE.TXT"
    sample_txt.write_text("uppercase txt", encoding="utf-8")
    r1 = runner.invoke(cli.cli, ["init", "upper-txt", "--file", str(sample_txt)])
    assert r1.exit_code == 0

    sample_md = tmp_path / "SAMPLE.MD"
    sample_md.write_text("uppercase md", encoding="utf-8")
    r2 = runner.invoke(cli.cli, ["init", "upper-md", "--file", str(sample_md)])
    assert r2.exit_code == 0


def test_init_and_stage_rows_integration(runner, fake_config):
    from shorts.project import Project
    from shorts.web.state import stage_rows

    r = runner.invoke(cli.cli, ["init", "integration-proj", "--text", "Sample idea prompt"])
    assert r.exit_code == 0

    project = Project.load(fake_config.projects_dir, "integration-proj")
    manifest = Manifest.load(project.manifest_path)
    rows = stage_rows(project, manifest, fake_config)
    by = {row["stage"]: row for row in rows}
    assert by["fetch"]["status"] == "skipped"
    assert by["transcribe"]["status"] == "skipped"
    assert by["ideate"]["status"] == "ready"


def test_init_with_count(runner, fake_config):
    r = runner.invoke(cli.cli, ["init", "count-proj", "--text", "content", "--count", "5"])
    assert r.exit_code == 0
    project_dir = fake_config.projects_dir / "count-proj"
    manifest = Manifest.load(project_dir / "manifest.json")
    assert manifest.settings.get("count") == 5
    assert manifest.get_setting("count") == 5


def test_init_with_count_zero(runner, fake_config):
    r = runner.invoke(cli.cli, ["init", "zero-count-proj", "--text", "content", "--count", "0"])
    assert r.exit_code != 0


def test_init_without_count(runner, fake_config):
    r = runner.invoke(cli.cli, ["init", "no-count-proj", "--text", "content"])
    assert r.exit_code == 0
    project_dir = fake_config.projects_dir / "no-count-proj"
    manifest = Manifest.load(project_dir / "manifest.json")
    assert "count" not in manifest.settings
    assert manifest.get_setting("count") is None


def test_fetch_with_count(runner, fake_config, monkeypatch):
    import shorts.stages.fetch as fetch_stage
    monkeypatch.setattr(fetch_stage, "probe_title", lambda url: "fetched-title")
    monkeypatch.setattr(fetch_stage, "run", lambda project, config, url, force: None)

    r = runner.invoke(cli.cli, ["fetch", "https://youtube.com/watch?v=abc", "--name", "fetch-proj", "--count", "5"])
    assert r.exit_code == 0
    project_dir = fake_config.projects_dir / "fetch-proj"
    manifest = Manifest.load(project_dir / "manifest.json")
    assert manifest.get_setting("count") == 5


def test_fetch_with_count_zero(runner, fake_config):
    r = runner.invoke(cli.cli, ["fetch", "https://youtube.com/watch?v=abc", "--name", "fetch-proj", "--count", "0"])
    assert r.exit_code != 0

