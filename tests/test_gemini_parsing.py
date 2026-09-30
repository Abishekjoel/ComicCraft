import json

import pytest

from app.errors import ConfigurationError, InvalidStoryError
from app.models.schemas import ComicRequest
from app.services import gemini_service
from app.services.gemini_service import extract_json, parse_story
from app.utils.prompt_builder import build_image_prompt, build_story_prompt
from tests.conftest import VALID_REQUEST, make_story_dict


def test_plain_json(story_json):
    assert parse_story(story_json, 3).title.startswith("The Fox")


def test_json_in_markdown_fence(story_json):
    assert len(parse_story(f"Here you go:\n```json\n{story_json}\n```\nEnjoy!", 3).panels) == 3


def test_json_with_surrounding_prose(story_json):
    assert len(parse_story(f"Sure! {story_json} Hope that helps.", 3).panels) == 3


@pytest.mark.parametrize("text", ["", "   ", "not json at all", "[1, 2, 3]", "{broken"])
def test_garbage_rejected(text):
    with pytest.raises(InvalidStoryError):
        extract_json(text)


def test_too_few_panels_rejected(story_json):
    with pytest.raises(InvalidStoryError):
        parse_story(story_json, 5)


def test_extra_panels_truncated_and_renumbered():
    data = make_story_dict(6)
    data["panels"][0]["panel_number"] = 99
    story = parse_story(json.dumps(data), 4)
    assert [p.panel_number for p in story.panels] == [1, 2, 3, 4]


def test_missing_key_gives_clear_configuration_error(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(ConfigurationError, match="GEMINI_API_KEY"):
        gemini_service.generate_story(ComicRequest(**VALID_REQUEST))


def test_invalid_output_is_retried_once(monkeypatch, story_json):
    replies = iter(["oops", story_json])
    monkeypatch.setattr(gemini_service, "_call_gemini", lambda p: next(replies))
    assert len(gemini_service.generate_story(ComicRequest(**VALID_REQUEST)).panels) == 3


def test_story_prompt_contains_brief():
    prompt = build_story_prompt(ComicRequest(**VALID_REQUEST))
    for needle in ["Finn", "Enchanted forest", "dramatic", "anime", "3-panel", "NEVER include dialogue"]:
        assert needle in prompt


def test_image_prompt_has_style_first_and_no_dialogue():
    req = ComicRequest(**VALID_REQUEST)
    story = parse_story(json.dumps(make_story_dict()), 3)
    prompt = build_image_prompt(story.panels[0], req, story.character_appearance)
    assert prompt.startswith("anime style")
    assert "Let us go" not in prompt
