import json

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.services import comic_service, gemini_service, image_service

VALID_REQUEST = {
    "prompt": "A brave fox exploring an enchanted forest",
    "character_name": "Finn",
    "setting": "Enchanted forest",
    "tone": "dramatic",
    "art_style": "anime",
    "panel_count": 3,
}


def make_story_dict(n: int = 3) -> dict:
    return {
        "title": "The Fox and the “Enchanted” Forest",
        "character_appearance": "young red fox, green scarf, amber eyes",
        "panels": [
            {
                "panel_number": i,
                "title": f"Part {i}",
                "scene_description": f"Finn walks deeper into the forest, scene {i}.",
                "narration": "The trees whispered — and Finn listened. " * 6,
                "dialogue": [{"character": "Finn", "text": "Let us go! " * 12}],
                "image_prompt": "young red fox, green scarf, amber eyes, forest path, wide shot, moonlight",
            }
            for i in range(1, n + 1)
        ],
    }


@pytest.fixture()
def story_json() -> str:
    return json.dumps(make_story_dict())


@pytest.fixture()
def generated_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(comic_service, "GENERATED_DIR", tmp_path)
    return tmp_path


@pytest.fixture()
def fake_pipeline(monkeypatch, generated_dir):
    """Replace ONLY the network/GPU edges (Gemini call + Diffusers) so the rest of the app runs for real."""
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(gemini_service, "_call_gemini", lambda prompt: json.dumps(make_story_dict()))

    def fake_generate_image(prompt, seed, out_path, negative_prompt=None):
        Image.new("RGB", (576, 448), (seed % 255, 120, 200)).save(out_path)
        return out_path

    monkeypatch.setattr(image_service, "generate_image", fake_generate_image)
    monkeypatch.setattr(image_service, "is_loaded", lambda: True)


@pytest.fixture()
def client():
    from app.main import app

    return TestClient(app)
