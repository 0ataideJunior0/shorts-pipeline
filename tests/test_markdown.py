from shorts.markdown import (
    IdeaSpec,
    ParsedIdea,
    parse_idea_file,
    prefixed_slug,
    render_idea,
)

SPEC = IdeaSpec(
    slug="morning-routine",
    title="The 5am routine that changed everything",
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
