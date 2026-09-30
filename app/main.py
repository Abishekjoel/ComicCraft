"""ComicCraft FastAPI application. Run with:  uvicorn app.main:app --reload"""
import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import GENERATED_DIR, STATIC_DIR, get_settings
from app.errors import ComicCraftError
from app.routes import comic, export
from app.services import image_service
from app.templating import templates

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = FastAPI(title="ComicCraft", version="1.0.0")
GENERATED_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.include_router(comic.router)
app.include_router(export.router)


@app.exception_handler(ComicCraftError)
async def comiccraft_error_handler(request: Request, exc: ComicCraftError):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message, "code": exc.code})


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    problems = []
    for err in exc.errors():
        field = ".".join(str(p) for p in err["loc"] if p not in ("body", "query", "path"))
        problems.append(f"{field}: {err['msg']}" if field else err["msg"])
    return JSONResponse(status_code=422, content={"detail": "; ".join(problems), "code": "invalid_input"})


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(request, "index.html", {"gemini_configured": get_settings().gemini_configured})


@app.get("/health")
def health():
    settings = get_settings()
    return {"status": "ok", "gemini_configured": settings.gemini_configured, **image_service.status()}
