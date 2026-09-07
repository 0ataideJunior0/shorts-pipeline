import json

import pytest

from shorts.web.edits import (
    EditError,
    apply_idea_edit,
    build_prompt_json,
    validate_plan_text,
)

IDEA_MD = (
    "---\nslug: 01-x\ntitle: old title\n---\n\n"
    "- [ ] Approved\n\n"
    "## Description\n\nold description\n\n"
    "## Tags\n\nold, tags\n\n"
    "## Hook\n\nh\n\n"
    "## Narration\n\nold\n\n"
    "## Notes\n\nn\n"
)


def _edit(md, **over):
    kw = dict(title="t", description="d", tags="a, b", narration="n", approved=False)
    kw.update(over)
    return apply_idea_edit(md, **kw)


def test_apply_idea_edit_sets_all_fields():
    out = _edit(
        IDEA_MD,
        title="New Title",
        description="A fresh caption for the short.",
        tags="gta 6, rockstar, leonida",
        narration="new script",
        approved=True,
    )
    assert "title: New Title\n" in out
    assert "## Description\n\nA fresh caption for the short.\n" in out
    assert "## Tags\n\ngta 6, rockstar, leonida\n" in out
    assert "## Narration\n\nnew script\n" in out
    assert "- [x] Approved" in out
    assert "## Hook\n\nh" in out
    assert "## Notes\n\nn" in out


def test_apply_idea_edit_flattens_multiline_title():
    out = _edit(IDEA_MD, title="line one\nline two")
    assert "title: line one line two\n" in out


def test_apply_idea_edit_bad_file_raises_editerror():
    with pytest.raises(EditError):
        _edit("nothing useful")


def test_apply_idea_edit_missing_description_section_raises():
    no_desc = (
        "---\nslug: 01-x\ntitle: t\n---\n\n- [ ] Approved\n\n"
        "## Narration\n\nx\n\n## Notes\n\nn\n"
    )
    with pytest.raises(EditError):
        _edit(no_desc)


def test_apply_idea_edit_missing_tags_section_raises():
    no_tags = (
        "---\nslug: 01-x\ntitle: t\n---\n\n- [ ] Approved\n\n"
        "## Description\n\nd\n\n## Narration\n\nx\n\n## Notes\n\nn\n"
    )
    with pytest.raises(EditError):
        _edit(no_tags)


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
