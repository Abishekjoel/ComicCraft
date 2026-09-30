import pytest
from pydantic import ValidationError

from app.models.schemas import ComicRequest, ExportRequest, Story
from tests.conftest import VALID_REQUEST, make_story_dict


def test_valid_request_normalises():
    req = ComicRequest(**{**VALID_REQUEST, "tone": " Dramatic ", "art_style": "Comic Book", "prompt": "  a   fox  "})
    assert req.tone == "dramatic" and req.art_style == "comic book" and req.prompt == "a fox"


def test_default_panel_count_is_four():
    data = {k: v for k, v in VALID_REQUEST.items() if k != "panel_count"}
    assert ComicRequest(**data).panel_count == 4


@pytest.mark.parametrize(
    "change",
    [
        {"prompt": ""}, {"prompt": "  "}, {"character_name": ""}, {"setting": " "},
        {"tone": "sarcastic"}, {"art_style": "pixel art"}, {"panel_count": 2}, {"panel_count": 7},
        {"prompt": "x" * 1001},
    ],
)
def test_invalid_requests_rejected(change):
    with pytest.raises(ValidationError):
        ComicRequest(**{**VALID_REQUEST, **change})


def test_story_schema_accepts_null_fields():
    data = make_story_dict()
    data["panels"][0]["dialogue"] = None
    data["panels"][0]["narration"] = None
    story = Story.model_validate(data)
    assert story.panels[0].dialogue == [] and story.panels[0].narration == ""


def test_story_schema_rejects_missing_image_prompt():
    data = make_story_dict()
    del data["panels"][0]["image_prompt"]
    with pytest.raises(ValidationError):
        Story.model_validate(data)


def test_export_request_rejects_path_traversal():
    with pytest.raises(ValidationError):
        ExportRequest(comic_id="../../etc/passwd")
