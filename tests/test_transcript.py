import pytest

from shorts.transcript import (
    Segment,
    chunk_plan,
    segments_to_text,
    shift_segments,
    stitch,
)


def test_chunk_plan_exact_division():
    assert chunk_plan(30.0, 10.0) == [(0.0, 10.0), (10.0, 20.0), (20.0, 30.0)]


def test_chunk_plan_with_remainder():
    assert chunk_plan(25.0, 10.0) == [(0.0, 10.0), (10.0, 20.0), (20.0, 25.0)]


def test_chunk_plan_single_chunk_when_chunk_bigger_than_total():
    assert chunk_plan(8.0, 100.0) == [(0.0, 8.0)]


def test_chunk_plan_rejects_bad_input():
    with pytest.raises(ValueError):
        chunk_plan(0, 10)
    with pytest.raises(ValueError):
        chunk_plan(10, 0)


def test_shift_segments():
    segs = [Segment(0.0, 1.0, "a"), Segment(1.0, 2.0, "b")]
    shifted = shift_segments(segs, 10.0)
    assert [(s.start, s.end) for s in shifted] == [(10.0, 11.0), (11.0, 12.0)]
    assert [(s.start, s.end) for s in segs] == [(0.0, 1.0), (1.0, 2.0)]


def test_stitch_applies_offset_and_sorts():
    chunk_a = (0.0, [Segment(0.0, 1.0, "one")])
    chunk_b = (10.0, [Segment(0.0, 1.0, "two"), Segment(1.0, 2.0, "three")])
    result = stitch([chunk_b, chunk_a])
    assert [s.text for s in result] == ["one", "two", "three"]
    assert [s.start for s in result] == [0.0, 10.0, 11.0]


def test_segments_to_text_collapses_whitespace():
    segs = [Segment(0, 1, "  hello  world "), Segment(1, 2, "\nfoo\tbar"), Segment(2, 3, "  ")]
    assert segments_to_text(segs) == "hello world foo bar"
