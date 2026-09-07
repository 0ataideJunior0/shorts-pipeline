import pytest

from shorts.markdown import (
    IdeaSpec,
    ParsedIdea,
    parse_idea_file,
    prefixed_slug,
    render_idea,
    replace_section,
    set_approved,
    set_frontmatter_value,
)

SPEC = IdeaSpec(
    slug="morning-routine",
    title="The 5am routine that changed everything",
    description="A three-step morning that fixed my focus. Try it tomorrow.",
    hook="You are waking up wrong.",
    narration_script="Here is the routine.\nStep one: sunlight.",
    asset_categories=["sunrise", "coffee"],
    source_start="12:30",
    source_end="14:05",
    est_duration_sec=42,
)


def test_prefixed_slug():
    assert prefixed_slug(1, "morning-routine") == "01-morning-routine"
    assert prefixed_slug(12, "x") == "12-x"


def test_render_contains_template_parts():
    md = render_idea(SPEC, 1)
    assert "slug: 01-morning-routine" in md
    assert 'source_range: "12:30-14:05"' in md
    assert "asset_categories: [sunrise, coffee]" in md
    assert "- [ ] Approved" in md
    assert "## Description\n\nA three-step morning that fixed my focus." in md
    assert "## Hook" in md
    assert "## Narration" in md
    assert "Step one: sunlight." in md
    assert "Suggested asset categories: sunrise, coffee" in md


def test_roundtrip_unapproved():
    md = render_idea(SPEC, 3)
    parsed = parse_idea_file(md)
    assert isinstance(parsed, ParsedIdea)
    assert parsed.slug == "03-morning-routine"
    assert parsed.approved is False
    assert parsed.narration == "Here is the routine.\nStep one: sunlight."
    assert parsed.description == "A three-step morning that fixed my focus. Try it tomorrow."


def test_approved_detection():
    md = render_idea(SPEC, 1).replace("- [ ] Approved", "- [x] Approved")
    assert parse_idea_file(md).approved is True
    md_upper = render_idea(SPEC, 1).replace("- [ ] Approved", "- [X] Approved")
    assert parse_idea_file(md_upper).approved is True


def test_narration_stops_at_next_heading():
    text = (
        "---\nslug: 01-x\n---\n\n- [ ] Approved\n\n"
        "## Narration\n\nreal narration here\n\n## Notes\n\nignore me\n"
    )
    assert parse_idea_file(text).narration == "real narration here"


def test_missing_frontmatter():
    parsed = parse_idea_file("## Narration\n\nhi\n")
    assert parsed.slug == ""
    assert parsed.frontmatter == {}
    assert parsed.narration == "hi"


IDEA_MD = (
    "---\nslug: 01-x\ntitle: T\n---\n\n"
    "- [ ] Approved\n\n"
    "## Hook\n\nthe hook\n\n"
    "## Narration\n\nold narration\nsecond line\n\n"
    "## Notes\n\nkeep me\n"
)


def test_replace_section_swaps_only_that_section():
    out = replace_section(IDEA_MD, "Narration", "brand new script")
    assert "## Narration\n\nbrand new script\n" in out
    assert "old narration" not in out
    assert "## Hook\n\nthe hook" in out
    assert "## Notes\n\nkeep me" in out
    assert out.startswith("---\nslug: 01-x")


def test_replace_section_strips_body_and_is_idempotent():
    once = replace_section(IDEA_MD, "Narration", "  padded  ")
    twice = replace_section(once, "Narration", "padded")
    assert once == twice
    assert "\n\npadded\n\n## Notes" in once


def test_replace_section_last_section_at_eof():
    out = replace_section(IDEA_MD, "Notes", "new notes")
    assert out.rstrip().endswith("## Notes\n\nnew notes")


def test_replace_section_missing_raises():
    with pytest.raises(ValueError):
        replace_section(IDEA_MD, "Nonexistent", "x")


def test_set_frontmatter_value_replaces_line():
    out = set_frontmatter_value(IDEA_MD, "title", "A brand new title")
    assert "title: A brand new title" in out
    assert "title: T\n" not in out
    assert out.startswith("---\nslug: 01-x")
    assert parse_idea_file(out).frontmatter["title"] == "A brand new title"


def test_set_frontmatter_value_flattens_newlines():
    out = set_frontmatter_value(IDEA_MD, "title", "  line one\n  line two  ")
    assert "title: line one line two\n" in out


def test_set_frontmatter_value_missing_key_raises():
    with pytest.raises(ValueError):
        set_frontmatter_value(IDEA_MD, "description", "x")


def test_set_frontmatter_value_no_block_raises():
    with pytest.raises(ValueError):
        set_frontmatter_value("no frontmatter here", "title", "x")


def test_set_approved_toggles_checkbox():
    approved = set_approved(IDEA_MD, True)
    assert "- [x] Approved" in approved
    assert "- [ ] Approved" not in approved
    back = set_approved(approved, False)
    assert "- [ ] Approved" in back
    assert "- [x] Approved" not in back


def test_set_approved_preserves_surrounding_blank_lines():
    out = set_approved(IDEA_MD, True)
    assert "---\n\n- [x] Approved\n\n## Hook" in out


def test_set_approved_missing_raises():
    with pytest.raises(ValueError):
        set_approved("no checkbox here", True)
