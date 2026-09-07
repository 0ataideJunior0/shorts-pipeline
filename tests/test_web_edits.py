import json

import pytest

from shorts.web.edits import (
    EditError,
    apply_idea_edit,
    build_prompt_json,
    validate_plan_text,
)

IDEA_MD = (
    "---\nslug: 01-x\n---\n\n"
    "- [ ] Approved\n\n"
    "## Hook\n\nh\n\n"
    "## Narration\n\nold\n\n"
    "## Notes\n\nn\n"
)


def test_apply_idea_edit_sets_narration_and_approval():
    out = apply_idea_edit(IDEA_MD, narration="new script", approved=True)
    assert "## Narration\n\nnew script\n" in out
    assert "- [x] Approved" in out
    assert "## Notes\n\nn" in out


def test_apply_idea_edit_bad_file_raises_editerror():
    with pytest.raises(EditError):
        apply_idea_edit("nothing useful", narration="x", approved=False)


def test_build_prompt_json_shape():
    out = build_prompt_json("faça vídeos curtos")
    assert out.endswith("\n")
    assert json.loads(out) == {"prompt": "faça vídeos curtos"}
    assert "faça" in out  # ensure_ascii=False


def test_build_prompt_json_empty_raises():
    with pytest.raises(EditError):
        build_prompt_json("   ")


def test_validate_plan_text_ok_roundtrips():
    src = '{"audio_path":"a.mp3","beats":[{"start":0,"end":1}]}'
    out = validate_plan_text(src)
    assert json.loads(out)["beats"][0]["end"] == 1
    assert out.endswith("\n")
    assert "\n  " in out  # pretty-printed


def test_validate_plan_text_bad_json_raises():
    with pytest.raises(EditError):
        validate_plan_text("{not json")


def test_validate_plan_text_missing_beats_raises():
    with pytest.raises(EditError):
        validate_plan_text('{"audio_path":"a.mp3"}')
