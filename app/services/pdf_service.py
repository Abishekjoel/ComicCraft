"""Glue between saved comics and the PDF exporter."""
from __future__ import annotations

import logging
import re
from datetime import datetime

import exporters
import layout_builder
from app.errors import NotFoundError, PDFError
from app.models.schemas import ComicResponse
from app.services.comic_service import comic_dir, load_comic

log = logging.getLogger("comiccraft.pdf")

PDF_NAME_RE = re.compile(r"^comic_\d{8}_\d{6}\.pdf$")


def export_comic_pdf(comic_id: str) -> tuple[ComicResponse, str]:
    """Create a timestamped PDF inside the comic's folder. Returns (comic, filename)."""
    comic = load_comic(comic_id)
    folder = comic_dir(comic_id)
    filename = datetime.now().strftime("comic_%Y%m%d_%H%M%S.pdf")
    try:
        pages = layout_builder.build_layout(comic.model_dump(), folder)
        exporters.export_pdf(pages, folder / filename)
    except FileNotFoundError as exc:
        raise PDFError("A panel image is missing, so the PDF could not be built. Regenerate the comic.") from exc
    except Exception as exc:
        log.exception("PDF export failed")
        raise PDFError(f"PDF generation failed: {exc}") from exc
    return comic, filename


def pdf_path(comic_id: str, filename: str):
    if not PDF_NAME_RE.match(filename):
        raise NotFoundError("File not found.")
    path = comic_dir(comic_id) / filename
    if not path.is_file():
        raise NotFoundError("File not found.")
    return path
