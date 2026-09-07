import textwrap
from pathlib import Path

import pytest

from shorts.config import load_config, ConfigError


def _write(root: Path, *, toml: str | None = None, env_key: str | None = "sk-test",
           make_assets: bool = True) -> Path:
    assets = root / "assets"
    if make_assets:
        assets.mkdir()
    default_toml = textwrap.dedent(f"""
        projects_dir = "projects"
        assets_dir = "{assets}"
        aspect = "9:16"

        [transcribe]
        model = "whisper-1"

        [ideate]
        model = "gpt-4.1"
        count = 6

        [voice]
        model = "gpt-4o-mini-tts"
        voice = "alloy"

        [render]
        min_beat_duration = 3.0
    """)
    (root / "config.toml").write_text(toml if toml is not None else default_toml)
    if env_key is not None:
        (root / ".env").write_text(f"OPENAI_API_KEY={env_key}\n")
    return root


@pytest.fixture(autouse=True)
def _clear_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)


def test_loads_valid_config(tmp_path):
    _write(tmp_path)
    cfg = load_config(tmp_path)
    assert cfg.projects_dir == (tmp_path / "projects").resolve()
    assert cfg.assets_dir == (tmp_path / "assets")
    assert cfg.aspect == "9:16"
    assert cfg.ideate.count == 6
    assert cfg.voice.voice == "alloy"
    assert cfg.voice.instructions is None
    assert cfg.voice.speed is None
    assert cfg.render.min_beat_duration == 3.0
    assert cfg.render.subtitle.enabled is True  # default when table absent
    assert cfg.render.subtitle.font is None
    assert cfg.render.subtitle.bold is False
    assert cfg.render.subtitle.position is None
    assert cfg.openai_api_key == "sk-test"


def _write_render_subtitle(tmp_path, body: str):
    assets = tmp_path / "assets"
    assets.mkdir()
    (tmp_path / "config.toml").write_text(
        f'projects_dir="projects"\nassets_dir="{assets}"\n\n[render.subtitle]\n{body}'
    )
    (tmp_path / ".env").write_text("OPENAI_API_KEY=sk-test\n")


def test_render_subtitles_can_be_disabled(tmp_path):
    _write_render_subtitle(tmp_path, "enabled = false\n")
    assert load_config(tmp_path).render.subtitle.enabled is False


def test_render_subtitle_full_customization(tmp_path):
    _write_render_subtitle(tmp_path, (
        'font = "Montserrat"\n'
        "font_size = 18\n"
        'primary_color = "#FFCC00"\n'
        "bold = true\n"
        "italic = true\n"
        "uppercase = true\n"
        'position = "top"\n'
        "margin_vertical = 40\n"
        "max_chars_per_line = 32\n"
        "max_lines = 2\n"
        "max_duration = 4.0\n"
    ))
    sub = load_config(tmp_path).render.subtitle
    assert sub.enabled is True
    assert sub.font == "Montserrat"
    assert sub.font_size == 18
    assert sub.primary_color == "#FFCC00"
    assert (sub.bold, sub.italic, sub.uppercase) == (True, True, True)
    assert sub.position == "top"
    assert sub.margin_vertical == 40
    assert sub.max_chars_per_line == 32
    assert sub.max_lines == 2
    assert sub.max_duration == 4.0


def test_render_subtitle_bad_position(tmp_path):
    _write_render_subtitle(tmp_path, 'position = "sideways"\n')
    with pytest.raises(ConfigError, match="render.subtitle.position must be one of"):
        load_config(tmp_path)


def test_render_subtitle_bad_color(tmp_path):
    _write_render_subtitle(tmp_path, 'primary_color = "yellow"\n')
    with pytest.raises(ConfigError, match="render.subtitle.primary_color"):
        load_config(tmp_path)


def test_render_subtitle_bad_font_size(tmp_path):
    _write_render_subtitle(tmp_path, "font_size = 0\n")
    with pytest.raises(ConfigError, match="render.subtitle.font_size must be >= 1"):
        load_config(tmp_path)


def test_voice_instructions_and_speed(tmp_path):
    assets = tmp_path / "assets"
    assets.mkdir()
    (tmp_path / "config.toml").write_text(
        f'projects_dir="projects"\nassets_dir="{assets}"\n\n'
        '[voice]\ninstructions = "  calm, warm  "\nspeed = 1.25\n'
    )
    (tmp_path / ".env").write_text("OPENAI_API_KEY=sk-test\n")
    cfg = load_config(tmp_path)
    assert cfg.voice.instructions == "calm, warm"
    assert cfg.voice.speed == 1.25


def test_voice_blank_instructions_becomes_none(tmp_path):
    assets = tmp_path / "assets"
    assets.mkdir()
    (tmp_path / "config.toml").write_text(
        f'projects_dir="projects"\nassets_dir="{assets}"\n\n'
        '[voice]\ninstructions = "   "\n'
    )
    (tmp_path / ".env").write_text("OPENAI_API_KEY=sk-test\n")
    assert load_config(tmp_path).voice.instructions is None


def test_voice_speed_out_of_range(tmp_path):
    assets = tmp_path / "assets"
    assets.mkdir()
    (tmp_path / "config.toml").write_text(
        f'projects_dir="projects"\nassets_dir="{assets}"\n\n[voice]\nspeed = 5.0\n'
    )
    (tmp_path / ".env").write_text("OPENAI_API_KEY=sk-test\n")
    with pytest.raises(ConfigError, match="voice.speed must be between 0.25 and 4.0"):
        load_config(tmp_path)


def test_missing_config_file(tmp_path):
    with pytest.raises(ConfigError, match="config.toml not found"):
        load_config(tmp_path)


def test_missing_api_key(tmp_path):
    _write(tmp_path, env_key=None)
    with pytest.raises(ConfigError, match="OPENAI_API_KEY"):
        load_config(tmp_path)


def test_missing_assets_dir(tmp_path):
    _write(tmp_path, make_assets=False)
    with pytest.raises(ConfigError, match="assets_dir does not exist"):
        load_config(tmp_path)


def test_bad_aspect(tmp_path):
    _write(tmp_path, toml='projects_dir="projects"\nassets_dir="%s"\naspect="1:1"\n'
           % (tmp_path / "assets"))
    with pytest.raises(ConfigError, match="aspect must be one of"):
        load_config(tmp_path)


def test_bad_count(tmp_path):
    assets = tmp_path / "assets"
    assets.mkdir()
    (tmp_path / "config.toml").write_text(
        f'projects_dir="projects"\nassets_dir="{assets}"\n\n[ideate]\ncount=0\n')
    (tmp_path / ".env").write_text("OPENAI_API_KEY=sk-test\n")
    with pytest.raises(ConfigError, match="ideate.count must be >= 1"):
        load_config(tmp_path)


def test_invalid_toml(tmp_path):
    assets = tmp_path / "assets"
    assets.mkdir()
    (tmp_path / "config.toml").write_text("this is = = not toml")
    (tmp_path / ".env").write_text("OPENAI_API_KEY=sk-test\n")
    with pytest.raises(ConfigError, match="not valid TOML"):
        load_config(tmp_path)


def test_youtube_defaults_when_section_absent(tmp_path):
    _write(tmp_path)
    cfg = load_config(tmp_path)
    assert cfg.youtube.client_secret is None
    assert cfg.youtube.token_path == (tmp_path / ".youtube_token.json").resolve()
    assert cfg.youtube.category_id == 22


def test_youtube_section_parsed_and_resolved(tmp_path):
    assets = tmp_path / "assets"
    assets.mkdir()
    (tmp_path / "config.toml").write_text(
        f'projects_dir="projects"\nassets_dir="{assets}"\n\n'
        '[youtube]\nclient_secret = "creds/cs.json"\n'
        'token_path = "sub/tok.json"\ncategory_id = 20\n'
    )
    (tmp_path / ".env").write_text("OPENAI_API_KEY=sk-test\n")
    cfg = load_config(tmp_path)
    assert cfg.youtube.client_secret == str((tmp_path / "creds/cs.json").resolve())
    assert cfg.youtube.token_path == (tmp_path / "sub/tok.json").resolve()
    assert cfg.youtube.category_id == 20


def test_youtube_bad_category_id(tmp_path):
    assets = tmp_path / "assets"
    assets.mkdir()
    (tmp_path / "config.toml").write_text(
        f'projects_dir="projects"\nassets_dir="{assets}"\n\n[youtube]\ncategory_id = 0\n'
    )
    (tmp_path / ".env").write_text("OPENAI_API_KEY=sk-test\n")
    with pytest.raises(ConfigError, match="youtube.category_id must be > 0"):
        load_config(tmp_path)
