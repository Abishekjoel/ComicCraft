"""Pydantic models: API requests/responses and the story structure expected from Gemini."""
from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator

TONES = ["funny", "dramatic", "adventure", "emotional", "dark", "light-hearted", "mystery", "fantasy"]
ART_STYLES = [
    "comic book", "anime", "manga", "cartoon", "watercolor", "fantasy illustration", "cinematic",
]
COMIC_ID_RE = re.compile(r"^[a-f0-9]{32}$")


def _clean(value: str) -> str:
    return " ".join(value.split())


class ComicRequest(BaseModel):
    prompt: str = Field(min_length=3, max_length=1000)
    character_name: str = Field(min_length=1, max_length=50)
    setting: str = Field(min_length=1, max_length=200)
    tone: str
    art_style: str
    panel_count: int = Field(default=4, ge=3, le=6)

    @field_validator("prompt", "character_name", "setting", mode="before")
    @classmethod
    def _strip(cls, v):
        return _clean(v) if isinstance(v, str) else v

    @field_validator("tone", mode="after")
    @classmethod
    def _tone(cls, v: str) -> str:
        v = v.strip().lower()
        if v not in TONES:
            raise ValueError(f"must be one of: {', '.join(TONES)}")
        return v

    @field_validator("art_style", mode="after")
    @classmethod
    def _style(cls, v: str) -> str:
        v = v.strip().lower()
        if v not in ART_STYLES:
            raise ValueError(f"must be one of: {', '.join(ART_STYLES)}")
        return v


# ---- Story structure returned by Gemini -------------------------------------------------

class DialogueLine(BaseModel):
    character: str = Field(min_length=1, max_length=80)
    text: str = Field(min_length=1, max_length=400)


class StoryPanel(BaseModel):
    panel_number: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=120)
    scene_description: str = Field(min_length=1)
    narration: str = ""
    dialogue: list[DialogueLine] = Field(default_factory=list)
    image_prompt: str = Field(min_length=1)

    @field_validator("dialogue", mode="before")
    @classmethod
    def _none_to_list(cls, v):
        return [] if v is None else v

    @field_validator("narration", mode="before")
    @classmethod
    def _none_to_str(cls, v):
        return "" if v is None else v


class Story(BaseModel):
    title: str = Field(min_length=1, max_length=150)
    character_appearance: str = ""
    panels: list[StoryPanel] = Field(min_length=1)


# ---- API responses -----------------------------------------------------------------------

class Panel(StoryPanel):
    image_url: str
    seed: int


class ComicResponse(BaseModel):
    comic_id: str
    title: str
    character_name: str
    tone: str
    art_style: str
    created_at: str
    panels: list[Panel]


class JobStatus(BaseModel):
    job_id: str
    status: Literal["queued", "running", "done", "error"]
    message: str
    current: int = 0
    total: int = 0
    panels: list[Panel] = Field(default_factory=list)  # panels finished so far
    title: str | None = None
    comic: ComicResponse | None = None
    error: str | None = None


class ExportRequest(BaseModel):
    comic_id: str

    @field_validator("comic_id")
    @classmethod
    def _id(cls, v: str) -> str:
        if not COMIC_ID_RE.match(v):
            raise ValueError("invalid comic id")
        return v


class ExportResponse(BaseModel):
    comic_id: str
    title: str
    panel_count: int
    filename: str
    download_url: str
    success_url: str
