from datetime import datetime, timedelta, timezone

import pytest

from shorts.publish import (
    build_video_body, cadence_from_manifest, iso, parse_iso, resolve_schedule,
)

UTC = timezone.utc


def test_parse_iso_and_iso_roundtrip():
    dt = parse_iso("2026-09-10T09:00:00Z")
    assert dt == datetime(2026, 9, 10, 9, 0, tzinfo=UTC)
    assert iso(dt) == "2026-09-10T09:00:00Z"


def test_cadence_from_manifest():
    assert cadence_from_manifest({}) is None
    assert cadence_from_manifest({"interval_hours": 24}) is None
    c = cadence_from_manifest({"start": "2026-09-10T09:00:00Z"})
    assert c == {"start": datetime(2026, 9, 10, 9, 0, tzinfo=UTC),
                 "interval_hours": 24, "weekdays": None}


def test_build_video_body_no_schedule():
    body = build_video_body(
        title="T" * 130, description="d", tags=" a, b ,, c ",
        category_id=22, publish_at=None,
    )
    assert len(body["snippet"]["title"]) == 100
    assert body["snippet"]["tags"] == ["a", "b", "c"]
    assert body["snippet"]["categoryId"] == "22"
    assert body["status"] == {"privacyStatus": "private", "selfDeclaredMadeForKids": False}
    assert "publishAt" not in body["status"]


def test_build_video_body_with_schedule():
    body = build_video_body(
        title="t", description="d", tags="", category_id=20,
        publish_at=datetime(2026, 9, 11, 12, 30, tzinfo=UTC),
    )
    assert body["snippet"]["tags"] == []
    assert body["status"]["publishAt"] == "2026-09-11T12:30:00Z"


def test_resolve_schedule_override_beats_cadence():
    ov = datetime(2026, 9, 20, 8, 0, tzinfo=UTC)
    cad = {"start": datetime(2026, 9, 10, 9, 0, tzinfo=UTC),
           "interval_hours": 24, "weekdays": None}
    out = resolve_schedule(["a", "b"], {"a": ov}, cad, set())
    assert out["a"] == ov
    assert out["b"] == datetime(2026, 9, 10, 9, 0, tzinfo=UTC)


def test_resolve_schedule_sequential_slots_and_taken():
    start = datetime(2026, 9, 10, 9, 0, tzinfo=UTC)
    cad = {"start": start, "interval_hours": 24, "weekdays": None}
    taken = {start + timedelta(days=1)}  # slot k=1 already used
    out = resolve_schedule(["a", "b"], {}, cad, taken)
    assert out["a"] == start
    assert out["b"] == start + timedelta(days=2)  # k=1 skipped


def test_resolve_schedule_weekday_filter_skips():
    # 2026-09-12 is a Saturday (isoweekday 6); allow Mon-Fri only
    start = datetime(2026, 9, 12, 9, 0, tzinfo=UTC)
    cad = {"start": start, "interval_hours": 24, "weekdays": [1, 2, 3, 4, 5]}
    out = resolve_schedule(["a"], {}, cad, set())
    assert out["a"] == datetime(2026, 9, 14, 9, 0, tzinfo=UTC)  # Monday


def test_resolve_schedule_none_without_cadence():
    assert resolve_schedule(["a"], {}, None, set()) == {"a": None}


def test_resolve_schedule_impossible_filter_hits_cap():
    cad = {"start": datetime(2026, 9, 10, 9, 0, tzinfo=UTC),
           "interval_hours": 24, "weekdays": []}
    assert resolve_schedule(["a"], {}, cad, set()) == {"a": None}
