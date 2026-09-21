from unittest.mock import MagicMock
import pytest

from shorts.openai_helpers import refine_idea_text


def _mock_client(return_text: str | None = "") -> MagicMock:
    client = MagicMock()
    choice = MagicMock()
    choice.message.content = return_text
    client.chat.completions.create.return_value = MagicMock(choices=[choice])
    return client


def test_refine_idea_text_title_clean_output():
    client = _mock_client('  **"Title: Secrets of Python Generators"**  \n\nExtra ignored line')
    result = refine_idea_text(
        client,
        field="title",
        video_title="Python Deep Dive",
        hook="Did you know this about generators?",
        narration="Generators save memory by yielding items one by one.",
        current_title="Old Generator Title",
        model="gpt-4o-mini",
    )

    assert result == "Secrets of Python Generators"
    client.chat.completions.create.assert_called_once()
    call_kwargs = client.chat.completions.create.call_args.kwargs
    assert call_kwargs["model"] == "gpt-4o-mini"
    messages = call_kwargs["messages"]
    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert "single line" in messages[0]["content"].lower()
    assert messages[1]["role"] == "user"
    assert "Source video title: Python Deep Dive" in messages[1]["content"]
    assert "Hook: Did you know this about generators?" in messages[1]["content"]
    assert "Narration: Generators save memory" in messages[1]["content"]
    assert "Current title: Old Generator Title" in messages[1]["content"]
    assert "Refine the title." in messages[1]["content"]


def test_refine_idea_text_description_clean_output():
    client = _mock_client('```\n"Here is how generators actually work in Python. Subscribe for more tips!"\n```')
    result = refine_idea_text(
        client,
        field="description",
        current_description="Old description text.",
        narration="Generators save memory by yielding items one by one.",
        model="gpt-4o-mini",
    )

    assert result == "Here is how generators actually work in Python. Subscribe for more tips!"
    call_kwargs = client.chat.completions.create.call_args.kwargs
    messages = call_kwargs["messages"]
    assert messages[0]["role"] == "system"
    assert "1-3 sentence" in messages[0]["content"].lower()
    assert messages[1]["role"] == "user"
    assert "Current description: Old description text." in messages[1]["content"]
    assert "Refine the description." in messages[1]["content"]


def test_refine_idea_text_tags_clean_output():
    client = _mock_client('  " #python, #coding, #generators, #tech, #shorts "  ')
    result = refine_idea_text(
        client,
        field="tags",
        current_tags="python, programming",
        model="gpt-4o-mini",
    )

    assert result == "python, coding, generators, tech, shorts"
    call_kwargs = client.chat.completions.create.call_args.kwargs
    messages = call_kwargs["messages"]
    assert messages[0]["role"] == "system"
    assert "5-12 comma-separated" in messages[0]["content"].lower()
    assert "no '#'" in messages[0]["content"].lower()
    assert messages[1]["role"] == "user"
    assert "Current tags: python, programming" in messages[1]["content"]
    assert "Refine the tags." in messages[1]["content"]


def test_refine_idea_text_includes_user_prompt():
    client = _mock_client("Refined Result")
    result = refine_idea_text(
        client,
        field="title",
        user_prompt="make it punchier and under 40 chars",
        model="gpt-4o-mini",
    )

    assert result == "Refined Result"
    call_kwargs = client.chat.completions.create.call_args.kwargs
    messages = call_kwargs["messages"]
    assert "User instruction: make it punchier and under 40 chars" in messages[1]["content"]


def test_refine_idea_text_omits_user_prompt_when_empty():
    client = _mock_client("Refined Result")
    refine_idea_text(
        client,
        field="title",
        user_prompt="",
        model="gpt-4o-mini",
    )

    call_kwargs = client.chat.completions.create.call_args.kwargs
    messages = call_kwargs["messages"]
    assert "User instruction:" not in messages[1]["content"]


def test_refine_idea_text_invalid_field_raises():
    client = _mock_client()
    with pytest.raises(ValueError, match="invalid field: summary"):
        refine_idea_text(client, field="summary", model="gpt-4o-mini")

    with pytest.raises(ValueError, match="invalid field: "):
        refine_idea_text(client, field="", model="gpt-4o-mini")


def test_refine_idea_text_empty_completion():
    client = _mock_client(None)
    result = refine_idea_text(client, field="title", model="gpt-4o-mini")
    assert result == ""


def test_get_client():
    from shorts.openai_helpers import get_client

    c = get_client("sk-test1234")
    assert c.api_key == "sk-test1234"


def test_refine_idea_text_without_context():
    client = _mock_client("Clean Title")
    result = refine_idea_text(client, field="title", model="gpt-4o-mini")
    assert result == "Clean Title"
    messages = client.chat.completions.create.call_args.kwargs["messages"]
    assert messages[1]["content"] == "Refine the title."


def test_refine_idea_text_cleans_markdown_bold_and_backticks():
    client = _mock_client("`**Bold In Code**`")
    result = refine_idea_text(client, field="title", model="gpt-4o-mini")
    assert result == "Bold In Code"

