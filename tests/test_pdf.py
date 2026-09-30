from pathlib import Path

from PIL import Image

import exporters
import layout_builder
from tests.conftest import make_story_dict


def make_comic(folder: Path, n=3, size=(576, 448)) -> dict:
    panels = []
    for p in make_story_dict(n)["panels"]:
        name = f"panel_{p['panel_number']}.png"
        Image.new("RGB", size, (200, 100, 50)).save(folder / name)
        panels.append({**p, "image_url": f"/static/generated/x/{name}", "seed": 1})
    return {"title": "Test “Comic” — Café", "art_style": "anime", "tone": "dramatic", "panels": panels}


def test_layout_preserves_aspect_ratio(tmp_path):
    pages = layout_builder.build_layout(make_comic(tmp_path, size=(1000, 500)), tmp_path)
    assert [p.kind for p in pages] == ["cover", "panel", "panel", "panel"]
    box = pages[1].image_box
    assert abs(box.w / box.h - 2.0) < 0.01
    assert box.x >= layout_builder.MARGIN and box.x + box.w <= layout_builder.PAGE_W - layout_builder.MARGIN


def test_tall_image_fits_page(tmp_path):
    box = layout_builder.build_layout(make_comic(tmp_path, size=(400, 1200)), tmp_path)[1].image_box
    assert box.h <= layout_builder.MAX_IMAGE_H + 1e-6


def test_pdf_is_created(tmp_path):
    pages = layout_builder.build_layout(make_comic(tmp_path, n=4), tmp_path)
    out = exporters.export_pdf(pages, tmp_path / "out.pdf")
    assert out.read_bytes().startswith(b"%PDF")


def test_core_font_fallback_handles_unicode(tmp_path, monkeypatch):
    monkeypatch.setattr(exporters, "find_unicode_font", lambda: None)
    pages = layout_builder.build_layout(make_comic(tmp_path), tmp_path)
    assert exporters.export_pdf(pages, tmp_path / "core.pdf").stat().st_size > 1000


def test_very_long_text_wraps_without_error(tmp_path):
    comic = make_comic(tmp_path, n=3)
    comic["panels"][0]["narration"] = "word " * 800
    comic["panels"][0]["dialogue"] = [{"character": "Finn", "text": "blah " * 300}]
    pages = layout_builder.build_layout(comic, tmp_path)
    assert exporters.export_pdf(pages, tmp_path / "long.pdf").exists()
