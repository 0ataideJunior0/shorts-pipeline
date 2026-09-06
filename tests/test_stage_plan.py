import json

from shorts.config import SubtitleCfg
from shorts.stages.plan import (
    plan_categories,
    plan_opts_hash,
    subtitle_plan_args,
    warn_missing_categories,
)


def _sub(**over) -> SubtitleCfg:
    base = dict(
        enabled=True, font=None, font_size=None, primary_color=None,
        bold=False, italic=False, uppercase=False, position=None,
        margin_vertical=None, max_chars_per_line=None, max_lines=None,
        max_duration=None,
    )
    base.update(over)
    return SubtitleCfg(**base)


def _write_plan(path, categories):
    path.write_text(json.dumps({
        "audio_path": "a.mp3",
        "beats": [
            {"start": 0.0, "end": 1.0, "duration": 1.0, "description": "d",
             "category": c, "is_new_category": False}
            for c in categories
        ],
    }))


def test_plan_categories_sorted_and_deduped(tmp_path):
    p = tmp_path / "x.plan.json"
    _write_plan(p, ["running", "coffee", "running", "sunrise"])
    assert plan_categories(p) == ["coffee", "running", "sunrise"]


def test_plan_categories_ignores_missing_and_empty(tmp_path):
    p = tmp_path / "x.plan.json"
    p.write_text(json.dumps({"beats": [{"category": ""}, {"description": "no cat"}]}))
    assert plan_categories(p) == []


def test_warn_missing_categories_flags_absent_folders(tmp_path, capsys):
    assets = tmp_path / "assets"
    (assets / "coffee").mkdir(parents=True)
    p = tmp_path / "01-foo.plan.json"
    _write_plan(p, ["coffee", "running"])

    warn_missing_categories("plan", "01-foo", p, assets)
    out = capsys.readouterr().out
    assert "01-foo" in out
    assert "running" in out
    assert "coffee" not in out


def test_warn_missing_categories_silent_when_all_present(tmp_path, capsys):
    assets = tmp_path / "assets"
    (assets / "coffee").mkdir(parents=True)
    p = tmp_path / "01-foo.plan.json"
    _write_plan(p, ["coffee"])

    warn_missing_categories("render", "01-foo", p, assets)
    assert capsys.readouterr().out == ""


def test_subtitle_plan_args_disabled_is_empty():
    assert subtitle_plan_args(_sub(enabled=False, font="X")) == []


def test_subtitle_plan_args_minimal():
    assert subtitle_plan_args(_sub()) == ["--subtitles"]


def test_subtitle_plan_args_full():
    args = subtitle_plan_args(_sub(
        font="Montserrat", font_size=18, primary_color="#FFCC00",
        bold=True, italic=True, uppercase=True, position="top",
        margin_vertical=40, max_chars_per_line=32, max_lines=2, max_duration=4.0,
    ))
    assert args == [
        "--subtitles",
        "--subtitle-font", "Montserrat",
        "--subtitle-font-size", "18",
        "--subtitle-primary-color", "#FFCC00",
        "--subtitle-bold",
        "--subtitle-italic",
        "--subtitle-uppercase",
        "--subtitle-position", "top",
        "--subtitle-margin-vertical", "40",
        "--subtitle-max-chars-per-line", "32",
        "--subtitle-max-lines", "2",
        "--subtitle-max-duration", "4.0",
    ]


def test_plan_opts_hash_stable_and_sensitive():
    base = plan_opts_hash(min_beat_duration=3.0, subtitle_args=["--subtitles"])
    assert base == plan_opts_hash(min_beat_duration=3.0, subtitle_args=["--subtitles"])
    assert base != plan_opts_hash(min_beat_duration=5.0, subtitle_args=["--subtitles"])
    assert base != plan_opts_hash(min_beat_duration=3.0, subtitle_args=[])
    assert base != plan_opts_hash(
        min_beat_duration=3.0,
        subtitle_args=["--subtitles", "--subtitle-bold"],
    )
