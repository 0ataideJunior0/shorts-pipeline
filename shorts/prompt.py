from __future__ import annotations

import json
from pathlib import Path

from shorts.project import Project

PROMPT_FILENAME = "prompt.json"

DEFAULT_IDEATE_PROMPT = (
    "Você é um roteirista especializado em vídeos curtos verticais "
    "(Shorts, Reels, TikTok). A partir da transcrição de um vídeo longo, "
    "gere ideias de vídeos curtos independentes. Cada ideia deve ter um "
    "gancho forte nos primeiros segundos e um roteiro de narração de 30 a "
    "60 segundos quando lido em voz alta (cerca de 80 a 150 palavras). Use "
    "apenas informações presentes na transcrição. Escreva todos os textos "
    "em português do Brasil, com linguagem clara e informal."
)


class PromptError(Exception):
    pass


def default_prompt_doc() -> dict:
    return {"prompt": DEFAULT_IDEATE_PROMPT}


def ensure_prompt_file(project: Project) -> Path:
    """Create ``ideas/prompt.json`` with the default prompt if it is absent.

    An existing file is never modified.
    """
    path = project.prompt_path
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(default_prompt_doc(), indent=2, ensure_ascii=False) + "\n"
        )
    return path


def read_prompt(project: Project) -> str:
    """Return the creative brief from ``ideas/prompt.json``.

    Falls back to the default when the file is missing; raises ``PromptError``
    when the file exists but is malformed or has an empty ``prompt``.
    """
    path = project.prompt_path
    try:
        raw = path.read_text()
    except FileNotFoundError:
        return DEFAULT_IDEATE_PROMPT
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise PromptError(f"{path} is not valid JSON: {exc}") from exc
    if not isinstance(data, dict) or not str(data.get("prompt", "")).strip():
        raise PromptError(
            f'{path} must be a JSON object with a non-empty "prompt" string'
        )
    return str(data["prompt"])
