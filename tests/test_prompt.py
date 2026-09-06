import json

import pytest

from shorts.project import Project
from shorts.prompt import (
    DEFAULT_IDEATE_PROMPT,
    PromptError,
    default_prompt_doc,
    ensure_prompt_file,
    read_prompt,
)


def test_default_doc_is_ptbr():
    doc = default_prompt_doc()
    assert doc == {"prompt": DEFAULT_IDEATE_PROMPT}
    assert "português do brasil" in DEFAULT_IDEATE_PROMPT.lower()


def test_ensure_creates_when_absent(tmp_path):
    project = Project.create(tmp_path, "demo")
    path = ensure_prompt_file(project)
    assert path == project.prompt_path
    assert path.is_file()
    assert json.loads(path.read_text())["prompt"] == DEFAULT_IDEATE_PROMPT


def test_ensure_preserves_existing(tmp_path):
    project = Project.create(tmp_path, "demo")
    project.prompt_path.write_text('{"prompt": "meu prompt custom"}')
    ensure_prompt_file(project)
    assert json.loads(project.prompt_path.read_text())["prompt"] == "meu prompt custom"


def test_read_prompt_returns_text(tmp_path):
    project = Project.create(tmp_path, "demo")
    project.prompt_path.write_text('{"prompt": "abc"}')
    assert read_prompt(project) == "abc"


def test_read_prompt_missing_file_falls_back(tmp_path):
    project = Project.create(tmp_path, "demo")
    assert read_prompt(project) == DEFAULT_IDEATE_PROMPT


def test_read_prompt_rejects_bad_json(tmp_path):
    project = Project.create(tmp_path, "demo")
    project.prompt_path.write_text("{not json")
    with pytest.raises(PromptError, match="not valid JSON"):
        read_prompt(project)


def test_read_prompt_rejects_empty_prompt(tmp_path):
    project = Project.create(tmp_path, "demo")
    project.prompt_path.write_text('{"prompt": "   "}')
    with pytest.raises(PromptError, match="non-empty"):
        read_prompt(project)
