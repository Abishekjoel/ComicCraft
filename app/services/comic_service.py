"""Orchestrates the pipeline: validate -> Gemini story -> Stable Diffusion panels -> saved comic."""
from __future__ import annotations

import json
import logging
import random
import shutil
import threading
import uuid
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Callable

from app.config import GENERATED_DIR, get_settings
from app.errors import ComicCraftError, ConfigurationError, NotFoundError
from app.models.schemas import COMIC_ID_RE, ComicRequest, ComicResponse, JobStatus, Panel
from app.services import gemini_service, image_service
from app.utils.prompt_builder import build_image_prompt

log = logging.getLogger("comiccraft.comic")

# progress(message, current_panel, total_panels, title, finished_panels)
ProgressFn = Callable[[str, int, int, "str | None", "list[Panel]"], None]


def comic_dir(comic_id: str):
    if not COMIC_ID_RE.match(comic_id):
        raise NotFoundError("Comic not found.")
    return GENERATED_DIR / comic_id


def generate_comic(req: ComicRequest, progress: ProgressFn | None = None, comic_id: str | None = None) -> ComicResponse:
    notify = progress or (lambda *a: None)
    settings = get_settings()
    if not settings.gemini_configured:  # fail fast, before anything heavy happens
        raise ConfigurationError(
            "GEMINI_API_KEY is not set. Add your key to the .env file (see .env.example) and restart the server."
        )

    notify("Creating your story...", 0, req.panel_count, None, [])
    story = gemini_service.generate_story(req)

    comic_id = comic_id or uuid.uuid4().hex
    out_dir = comic_dir(comic_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    base_seed = settings.image_seed if settings.image_seed is not None else random.randint(0, 2**31 - 1)

    panels: list[Panel] = []
    try:
        for story_panel in story.panels:
            n = story_panel.panel_number
            if not image_service.is_loaded():
                notify(f"Loading the image model (the first run downloads it)... then panel {n}", n - 1,
                       req.panel_count, story.title, panels)
            else:
                notify(f"Generating panel {n} of {req.panel_count}...", n - 1, req.panel_count, story.title, panels)
            prompt = build_image_prompt(story_panel, req, story.character_appearance)
            seed = base_seed + n
            filename = f"panel_{n}.png"
            image_service.generate_image(prompt, seed, out_dir / filename)
            panels.append(
                Panel(**story_panel.model_dump(), image_url=f"/static/generated/{comic_id}/{filename}", seed=seed)
            )
            notify(f"Panel {n} done.", n, req.panel_count, story.title, panels)

        comic = ComicResponse(
            comic_id=comic_id,
            title=story.title,
            character_name=req.character_name,
            tone=req.tone,
            art_style=req.art_style,
            created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            panels=panels,
        )
        (out_dir / "comic.json").write_text(comic.model_dump_json(indent=2), encoding="utf-8")
        return comic
    except Exception:
        shutil.rmtree(out_dir, ignore_errors=True)  # don't leave half-finished comics behind
        raise


def load_comic(comic_id: str) -> ComicResponse:
    path = comic_dir(comic_id) / "comic.json"
    if not path.is_file():
        raise NotFoundError("Comic not found.")
    return ComicResponse.model_validate_json(path.read_text(encoding="utf-8"))


# ---- Background jobs (so the browser can show live progress) ------------------------------

_jobs: "OrderedDict[str, JobStatus]" = OrderedDict()
_jobs_lock = threading.Lock()
MAX_JOBS = 50


def create_job(req: ComicRequest) -> JobStatus:
    job_id = uuid.uuid4().hex
    job = JobStatus(job_id=job_id, status="queued", message="Queued...", total=req.panel_count)
    with _jobs_lock:
        _jobs[job_id] = job
        while len(_jobs) > MAX_JOBS:
            _jobs.popitem(last=False)
    return job


def get_job(job_id: str) -> JobStatus:
    with _jobs_lock:
        job = _jobs.get(job_id)
    if job is None:
        raise NotFoundError("Job not found (it may have expired).")
    return job


def _update_job(job_id: str, **changes) -> None:
    with _jobs_lock:
        job = _jobs.get(job_id)
        if job is not None:
            _jobs[job_id] = job.model_copy(update=changes)


def run_job(job_id: str, req: ComicRequest) -> None:
    """Runs in a worker thread. The comic_id equals the job_id."""

    def progress(message, current, total, title, panels):
        _update_job(job_id, status="running", message=message, current=current, total=total,
                    title=title, panels=list(panels))

    try:
        comic = generate_comic(req, progress, comic_id=job_id)
        _update_job(job_id, status="done", message="Your comic is ready!", current=len(comic.panels),
                    comic=comic, panels=comic.panels, title=comic.title)
    except ComicCraftError as exc:
        log.warning("Job %s failed: %s", job_id, exc.message)
        _update_job(job_id, status="error", message="Generation failed.", error=exc.message)
    except Exception:
        log.exception("Job %s crashed", job_id)
        _update_job(job_id, status="error", message="Generation failed.",
                    error="An unexpected error occurred. Check the server log for details.")
