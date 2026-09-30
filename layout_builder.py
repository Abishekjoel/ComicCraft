"""Prepares page layout data for the PDF export (pure geometry + text, no PDF library here)."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image

PAGE_W, PAGE_H = 210.0, 297.0  # A4 portrait, millimetres
MARGIN = 15.0
HEADER_H = 8.0
PANEL_TITLE_H = 12.0
MAX_IMAGE_H = 150.0  # keep room below the image for narration and dialogue


@dataclass
class ImageBox:
    x: float
    y: float
    w: float
    h: float


@dataclass
class PageLayout:
    kind: str  # "cover" or "panel"
    comic_title: str
    subtitle: str = ""
    panel_number: int = 0
    panel_title: str = ""
    image_path: Path | None = None
    image_box: ImageBox | None = None
    text_y: float = 0.0  # where narration/dialogue start
    narration: str = ""
    dialogue: list[tuple[str, str]] = field(default_factory=list)  # (character, text)


def fit_image(img_w: int, img_h: int, max_w: float, max_h: float, x0: float, y0: float) -> ImageBox:
    """Scale to fit inside max_w x max_h preserving aspect ratio, centred horizontally."""
    if img_w <= 0 or img_h <= 0:
        raise ValueError("Image has invalid dimensions")
    scale = min(max_w / img_w, max_h / img_h)
    w, h = img_w * scale, img_h * scale
    return ImageBox(x=x0 + (max_w - w) / 2, y=y0, w=w, h=h)


def build_layout(comic: dict, image_root: Path) -> list[PageLayout]:
    """comic: the comic as a plain dict (ComicResponse.model_dump()). image_root: folder holding panel images."""
    panels = comic["panels"]
    pages = [
        PageLayout(
            kind="cover",
            comic_title=comic["title"],
            subtitle=f"{len(panels)} panels  |  {comic['art_style'].title()}  |  {comic['tone'].title()}",
        )
    ]
    content_w = PAGE_W - 2 * MARGIN
    for panel in panels:
        image_path = image_root / Path(panel["image_url"]).name
        with Image.open(image_path) as img:
            iw, ih = img.size
        top = MARGIN + HEADER_H + PANEL_TITLE_H
        box = fit_image(iw, ih, content_w, MAX_IMAGE_H, MARGIN, top)
        pages.append(
            PageLayout(
                kind="panel",
                comic_title=comic["title"],
                panel_number=panel["panel_number"],
                panel_title=panel["title"],
                image_path=image_path,
                image_box=box,
                text_y=box.y + box.h + 8.0,
                narration=panel.get("narration", "") or "",
                dialogue=[(d["character"], d["text"]) for d in panel.get("dialogue", [])],
            )
        )
    return pages
