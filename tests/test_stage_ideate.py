from types import SimpleNamespace
from unittest.mock import MagicMock
from pathlib import Path
import pytest

from shorts.markdown import IdeaSpec
from shorts.project import Manifest, Project
from shorts.stages import ideate


def _sample_idea(slug: str = "sample-idea") -> IdeaSpec:
    return IdeaSpec(
        slug=slug,
        title="Sample Title",
        description="Sample Description",
        tags=["tag1", "tag2"],
        hook="Sample Hook",
        narration_script="Sample narration script text.",
        asset_categories=["category1"],
        source_start="00:00",
        source_end="00:30",
        est_duration_sec=30,
    )


def _setup_project(tmp_path: Path, name: str = "demo", *, manifest_count: int | None = None) -> Project:
    project = Project.create(tmp_path, name)
    project.transcript_txt_path.write_text("Test transcript content")
    manifest = Manifest.new(name)
    if manifest_count is not None:
        manifest.set_setting("count", manifest_count)
    manifest.save(project.manifest_path)
    return project


def _fake_config(count: int = 6, model: str = "gpt-4o-mini", api_key: str = "test-key") -> SimpleNamespace:
    return SimpleNamespace(
        openai_api_key=api_key,
        ideate=SimpleNamespace(model=model, count=count),
    )


def test_explicit_count_overrides_manifest_and_config(tmp_path, monkeypatch):
    project = _setup_project(tmp_path, manifest_count=5)
    config = _fake_config(count=6)

    mock_generate = MagicMock(return_value=[_sample_idea()])
    mock_client = MagicMock()
    monkeypatch.setattr(ideate, "get_client", lambda key: mock_client)
    monkeypatch.setattr(ideate, "generate_ideas", mock_generate)

    ideate.run(project, config, count=3)

    mock_generate.assert_called_once()
    assert mock_generate.call_args.kwargs["count"] == 3

    manifest = Manifest.load(project.manifest_path)
    stage = manifest.get_stage("ideate")
    assert stage is not None
    assert stage["status"] == "done"
    assert stage["count"] == 3


def test_manifest_count_overrides_config_when_explicit_count_is_none(tmp_path, monkeypatch):
    project = _setup_project(tmp_path, manifest_count=5)
    config = _fake_config(count=6)

    mock_generate = MagicMock(return_value=[_sample_idea()])
    mock_client = MagicMock()
    monkeypatch.setattr(ideate, "get_client", lambda key: mock_client)
    monkeypatch.setattr(ideate, "generate_ideas", mock_generate)

    ideate.run(project, config, count=None)

    mock_generate.assert_called_once()
    assert mock_generate.call_args.kwargs["count"] == 5

    manifest = Manifest.load(project.manifest_path)
    stage = manifest.get_stage("ideate")
    assert stage is not None
    assert stage["status"] == "done"
    assert stage["count"] == 5


def test_config_count_fallback_when_both_none(tmp_path, monkeypatch):
    project = _setup_project(tmp_path, manifest_count=None)
    config = _fake_config(count=6)

    mock_generate = MagicMock(return_value=[_sample_idea()])
    mock_client = MagicMock()
    monkeypatch.setattr(ideate, "get_client", lambda key: mock_client)
    monkeypatch.setattr(ideate, "generate_ideas", mock_generate)

    ideate.run(project, config, count=None)

    mock_generate.assert_called_once()
    assert mock_generate.call_args.kwargs["count"] == 6

    manifest = Manifest.load(project.manifest_path)
    stage = manifest.get_stage("ideate")
    assert stage is not None
    assert stage["status"] == "done"
    assert stage["count"] == 6


def test_manifest_stages_ideate_records_count_and_hashes(tmp_path, monkeypatch):
    project = _setup_project(tmp_path, manifest_count=4)
    config = _fake_config(count=8, model="test-model")

    mock_generate = MagicMock(return_value=[_sample_idea()])
    mock_client = MagicMock()
    monkeypatch.setattr(ideate, "get_client", lambda key: mock_client)
    monkeypatch.setattr(ideate, "generate_ideas", mock_generate)

    ideate.run(project, config, count=2)

    manifest = Manifest.load(project.manifest_path)
    stage = manifest.stages["ideate"]
    assert stage["model"] == "test-model"
    assert stage["count"] == 2
    assert "transcript_sha256" in stage
    assert "prompt_sha256" in stage
    assert stage["status"] == "done"


def test_invalid_or_nonpositive_manifest_count_falls_back_to_config(tmp_path, monkeypatch):
    project = _setup_project(tmp_path)
    # Manifest setting is non-positive or non-int
    manifest = Manifest.load(project.manifest_path)
    manifest.set_setting("count", 0)
    manifest.save(project.manifest_path)

    config = _fake_config(count=7)

    mock_generate = MagicMock(return_value=[_sample_idea()])
    mock_client = MagicMock()
    monkeypatch.setattr(ideate, "get_client", lambda key: mock_client)
    monkeypatch.setattr(ideate, "generate_ideas", mock_generate)

    ideate.run(project, config, count=None)

    assert mock_generate.call_args.kwargs["count"] == 7
    manifest = Manifest.load(project.manifest_path)
    assert manifest.stages["ideate"]["count"] == 7


def test_invalid_or_nonpositive_explicit_count_falls_back_to_manifest(tmp_path, monkeypatch):
    project = _setup_project(tmp_path, manifest_count=4)
    config = _fake_config(count=9)

    mock_generate = MagicMock(return_value=[_sample_idea()])
    mock_client = MagicMock()
    monkeypatch.setattr(ideate, "get_client", lambda key: mock_client)
    monkeypatch.setattr(ideate, "generate_ideas", mock_generate)

    ideate.run(project, config, count=0)

    assert mock_generate.call_args.kwargs["count"] == 4
    manifest = Manifest.load(project.manifest_path)
    assert manifest.stages["ideate"]["count"] == 4
