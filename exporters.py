"""PDF export with fpdf2. Takes the page layouts from layout_builder and draws them."""
from __future__ import annotations

import os
from pathlib import Path

from fpdf import FPDF

from layout_builder import MARGIN, PAGE_H, PAGE_W, PageLayout

# Unicode TTFs we can use so curly quotes, accents, etc. render. First existing file wins.
_FONT_CANDIDATES = [
    "C:/Windows/Fonts/arial.ttf",
    "C:/Windows/Fonts/segoeui.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans.ttf",
    "/Library/Fonts/Arial Unicode.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
]

_REPLACEMENTS = {
    "\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"', "\u2013": "-", "\u2014": "-",
    "\u2026": "...", "\u00a0": " ", "\u2022": "*",
}

INK = (20, 20, 30)
ACCENT = (230, 57, 70)
CAPTION_BG = (255, 241, 168)


def find_unicode_font() -> str | None:
    override = os.getenv("PDF_FONT_PATH", "").strip()
    for path in ([override] if override else []) + _FONT_CANDIDATES:
        if path and Path(path).is_file():
            return path
    return None


class ComicPDF(FPDF):
    def __init__(self, comic_title: str):
        super().__init__(orientation="P", unit="mm", format="A4")
        self.comic_title = comic_title
        self.show_header = False
        self.set_margins(MARGIN, MARGIN, MARGIN)
        self.set_auto_page_break(True, margin=MARGIN)
        font_path = find_unicode_font()
        self.unicode_font = False
        if font_path:
            try:
                self.add_font("Body", "", font_path)
                self.unicode_font = True
            except Exception:  # unreadable font: fall back to core fonts
                self.unicode_font = False
        self.set_title(self.txt(comic_title))
        self.set_creator("ComicCraft")

    # -- text helpers --
    def txt(self, text: str) -> str:
        """Return text safe for the active font (core fonts only support Latin-1)."""
        text = (text or "").replace("\r", "")
        if self.unicode_font:
            return text
        for src, dst in _REPLACEMENTS.items():
            text = text.replace(src, dst)
        return text.encode("latin-1", "replace").decode("latin-1")

    def use_font(self, style: str = "", size: float = 11) -> None:
        if self.unicode_font:
            self.set_font("Body", "", size)  # single regular face; bold/italic dropped
        else:
            self.set_font("Helvetica", style, size)

    def header(self) -> None:
        if not self.show_header:
            return
        self.set_y(MARGIN)
        self.use_font("B", 9)
        self.set_text_color(120, 120, 130)
        self.cell(0, 6, self.txt(self.comic_title), align="L")
        self.set_draw_color(*ACCENT)
        self.set_line_width(0.6)
        self.line(MARGIN, MARGIN + 7, PAGE_W - MARGIN, MARGIN + 7)

    def footer(self) -> None:
        if not self.show_header:
            return
        self.set_y(-12)
        self.use_font("", 8)
        self.set_text_color(150, 150, 160)
        self.cell(0, 6, f"ComicCraft  -  page {self.page_no()}", align="C")


def _draw_cover(pdf: ComicPDF, page: PageLayout) -> None:
    pdf.show_header = False
    pdf.add_page()
    pdf.set_fill_color(*ACCENT)
    pdf.rect(0, 0, PAGE_W, 70, style="F")
    pdf.set_y(PAGE_H / 2 - 30)
    pdf.set_text_color(*INK)
    pdf.use_font("B", 30)
    pdf.multi_cell(0, 14, pdf.txt(page.comic_title), align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    pdf.use_font("", 12)
    pdf.set_text_color(100, 100, 110)
    pdf.multi_cell(0, 7, pdf.txt(page.subtitle), align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_y(-30)
    pdf.use_font("B", 10)
    pdf.cell(0, 6, "Created with ComicCraft", align="C")


def _draw_panel(pdf: ComicPDF, page: PageLayout) -> None:
    pdf.show_header = True
    pdf.add_page()
    content_w = PAGE_W - 2 * MARGIN

    pdf.set_xy(MARGIN, MARGIN + 10)
    pdf.set_text_color(*INK)
    pdf.use_font("B", 14)
    pdf.multi_cell(content_w, 7, pdf.txt(f"Panel {page.panel_number}: {page.panel_title}"),
                   new_x="LMARGIN", new_y="NEXT")

    box = page.image_box
    pdf.image(str(page.image_path), x=box.x, y=box.y, w=box.w, h=box.h)
    pdf.set_draw_color(*INK)
    pdf.set_line_width(0.8)
    pdf.rect(box.x, box.y, box.w, box.h)

    pdf.set_xy(MARGIN, page.text_y)
    if page.narration.strip():
        pdf.set_fill_color(*CAPTION_BG)
        pdf.set_text_color(*INK)
        pdf.set_line_width(0.4)
        pdf.use_font("I", 11)
        pdf.multi_cell(content_w, 6, pdf.txt(page.narration.strip()), border=1, fill=True,
                       new_x="LMARGIN", new_y="NEXT")
        pdf.ln(4)

    for character, text in page.dialogue:
        pdf.set_x(MARGIN)
        pdf.set_text_color(*ACCENT)
        pdf.use_font("B", 11)
        pdf.write(6, pdf.txt(f"{character}: "))
        pdf.set_text_color(*INK)
        pdf.use_font("", 11)
        pdf.write(6, pdf.txt(text))
        pdf.ln(8)


def export_pdf(pages: list[PageLayout], out_path: Path) -> Path:
    """Render the layouts to out_path and return it."""
    if not pages:
        raise ValueError("Nothing to export")
    pdf = ComicPDF(pages[0].comic_title)
    for page in pages:
        if page.kind == "cover":
            _draw_cover(pdf, page)
        else:
            _draw_panel(pdf, page)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(out_path))
    return out_path
