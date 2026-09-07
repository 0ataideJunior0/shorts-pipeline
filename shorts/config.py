from __future__ import annotations

import os
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class TranscribeCfg:
    model: str


@dataclass(frozen=True)
class IdeateCfg:
    model: str
    count: int


@dataclass(frozen=True)
class VoiceCfg:
    model: str
    voice: str
    instructions: str | None
    speed: float | None


@dataclass(frozen=True)
class SubtitleCfg:
    enabled: bool
    font: str | None
    font_size: int | None
    primary_color: str | None
    bold: bool
    italic: bool
    uppercase: bool
    position: str | None
    margin_vertical: int | None
    max_chars_per_line: int | None
    max_lines: int | None
    max_duration: float | None


@dataclass(frozen=True)
class RenderCfg:
    min_beat_duration: float
    subtitle: SubtitleCfg


@dataclass(frozen=True)
class YouTubeCfg:
    client_secret: str | None
    token_path: Path
    category_id: int


@dataclass(frozen=True)
class Config:
    root: Path
    projects_dir: Path
    assets_dir: Path
    aspect: str
    transcribe: TranscribeCfg
    ideate: IdeateCfg
    voice: VoiceCfg
    render: RenderCfg
    openai_api_key: str
    youtube: YouTubeCfg


_ASPECTS = {"9:16", "16:9"}
_SUBTITLE_POSITIONS = {"bottom", "middle", "top"}
_HEX_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")


def _pos_int(value: object, key: str, *, minimum: int) -> int | None:
    if value is None:
        return None
    try:
        out = int(value)
    except (TypeError, ValueError):
        raise ConfigError(f"{key} must be an integer, got {value!r}") from None
    if out < minimum:
        raise ConfigError(f"{key} must be >= {minimum}, got {out}")
    return out


def _subtitle_cfg(s: dict) -> SubtitleCfg:
    color = s.get("primary_color")
    if color is not None:
        color = str(color)
        if not _HEX_COLOR.match(color):
            raise ConfigError(
                f"render.subtitle.primary_color must be a hex color #RRGGBB, "
                f"got {color!r}"
            )

    position = s.get("position")
    if position is not None:
        position = str(position)
        if position not in _SUBTITLE_POSITIONS:
            raise ConfigError(
                f"render.subtitle.position must be one of "
                f"{sorted(_SUBTITLE_POSITIONS)}, got {position!r}"
            )

    font = s.get("font")

    max_duration = s.get("max_duration")
    if max_duration is not None:
        max_duration = float(max_duration)
        if max_duration <= 0:
            raise ConfigError("render.subtitle.max_duration must be > 0")

    return SubtitleCfg(
        enabled=bool(s.get("enabled", True)),
        font=str(font) if font is not None else None,
        font_size=_pos_int(s.get("font_size"), "render.subtitle.font_size", minimum=1),
        primary_color=color,
        bold=bool(s.get("bold", False)),
        italic=bool(s.get("italic", False)),
        uppercase=bool(s.get("uppercase", False)),
        position=position,
        margin_vertical=_pos_int(
            s.get("margin_vertical"), "render.subtitle.margin_vertical", minimum=0
        ),
        max_chars_per_line=_pos_int(
            s.get("max_chars_per_line"),
            "render.subtitle.max_chars_per_line",
            minimum=1,
        ),
        max_lines=_pos_int(
            s.get("max_lines"), "render.subtitle.max_lines", minimum=1
        ),
        max_duration=max_duration,
    )


def load_config(root: Path | None = None) -> Config:
    root = Path(root or Path.cwd()).resolve()

    cfg_path = root / "config.toml"
    if not cfg_path.is_file():
        raise ConfigError(
            f"config.toml not found at {cfg_path} (copy config.example.toml)"
        )
    try:
        raw = tomllib.loads(cfg_path.read_text())
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"config.toml is not valid TOML: {exc}") from exc

    load_dotenv(root / ".env")
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise ConfigError("OPENAI_API_KEY is not set (put it in .env)")

    if "projects_dir" not in raw:
        raise ConfigError("config.toml missing required key: projects_dir")
    projects_dir = Path(str(raw["projects_dir"])).expanduser()
    if not projects_dir.is_absolute():
        projects_dir = (root / projects_dir).resolve()

    if "assets_dir" not in raw:
        raise ConfigError("config.toml missing required key: assets_dir")
    assets_dir = Path(str(raw["assets_dir"])).expanduser()
    if not assets_dir.is_dir():
        raise ConfigError(f"assets_dir does not exist: {assets_dir}")

    aspect = str(raw.get("aspect", "9:16"))
    if aspect not in _ASPECTS:
        raise ConfigError(
            f"aspect must be one of {sorted(_ASPECTS)}, got {aspect!r}"
        )

    t = raw.get("transcribe", {})
    i = raw.get("ideate", {})
    v = raw.get("voice", {})
    r = raw.get("render", {})

    count = int(i.get("count", 6))
    if count < 1:
        raise ConfigError("ideate.count must be >= 1")

    min_beat = float(r.get("min_beat_duration", 3.0))
    if min_beat <= 0:
        raise ConfigError("render.min_beat_duration must be > 0")

    subtitle = _subtitle_cfg(r.get("subtitle", {}))

    voice_instructions = v.get("instructions")
    if voice_instructions is not None:
        voice_instructions = str(voice_instructions).strip() or None

    voice_speed = v.get("speed")
    if voice_speed is not None:
        voice_speed = float(voice_speed)
        if not 0.25 <= voice_speed <= 4.0:
            raise ConfigError("voice.speed must be between 0.25 and 4.0")

    yt = raw.get("youtube", {})
    yt_secret = yt.get("client_secret")
    if yt_secret is not None:
        p = Path(str(yt_secret)).expanduser()
        yt_secret = str(p if p.is_absolute() else (root / p).resolve())
    yt_token = Path(str(yt.get("token_path", ".youtube_token.json"))).expanduser()
    if not yt_token.is_absolute():
        yt_token = (root / yt_token).resolve()
    yt_category = int(yt.get("category_id", 22))
    if yt_category <= 0:
        raise ConfigError("youtube.category_id must be > 0")

    return Config(
        root=root,
        projects_dir=projects_dir,
        assets_dir=assets_dir,
        aspect=aspect,
        transcribe=TranscribeCfg(model=str(t.get("model", "whisper-1"))),
        ideate=IdeateCfg(model=str(i.get("model", "gpt-4.1")), count=count),
        voice=VoiceCfg(
            model=str(v.get("model", "gpt-4o-mini-tts")),
            voice=str(v.get("voice", "alloy")),
            instructions=voice_instructions,
            speed=voice_speed,
        ),
        render=RenderCfg(min_beat_duration=min_beat, subtitle=subtitle),
        openai_api_key=api_key,
        youtube=YouTubeCfg(
            client_secret=yt_secret,
            token_path=yt_token,
            category_id=yt_category,
        ),
    )
