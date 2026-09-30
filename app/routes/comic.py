from fastapi import APIRouter, BackgroundTasks

from app.models.schemas import ComicRequest, ComicResponse, JobStatus
from app.services import comic_service

router = APIRouter(prefix="/api/comic", tags=["comic"])


@router.post("/generate", response_model=ComicResponse)
def generate(req: ComicRequest) -> ComicResponse:
    """Generate a full comic and return it when finished (can take minutes on slow hardware)."""
    return comic_service.generate_comic(req)


@router.post("/jobs", response_model=JobStatus, status_code=202)
def start_job(req: ComicRequest, background: BackgroundTasks) -> JobStatus:
    """Start generation in the background; poll GET /api/comic/jobs/{job_id} for progress."""
    job = comic_service.create_job(req)
    background.add_task(comic_service.run_job, job.job_id, req)
    return job


@router.get("/jobs/{job_id}", response_model=JobStatus)
def job_status(job_id: str) -> JobStatus:
    return comic_service.get_job(job_id)


@router.get("/{comic_id}", response_model=ComicResponse)
def get_comic(comic_id: str) -> ComicResponse:
    return comic_service.load_comic(comic_id)
