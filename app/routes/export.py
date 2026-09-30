from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, HTMLResponse

from app.models.schemas import ExportRequest, ExportResponse
from app.services import comic_service, pdf_service
from app.templating import templates

router = APIRouter(tags=["export"])


@router.post("/api/comic/export", response_model=ExportResponse)
def export_comic(req: ExportRequest) -> ExportResponse:
    comic, filename = pdf_service.export_comic_pdf(req.comic_id)
    return ExportResponse(
        comic_id=comic.comic_id,
        title=comic.title,
        panel_count=len(comic.panels),
        filename=filename,
        download_url=f"/api/export/download/{comic.comic_id}/{filename}",
        success_url=f"/export/success?comic_id={comic.comic_id}&file={filename}",
    )


@router.get("/api/export/download/{comic_id}/{filename}")
def download_pdf(comic_id: str, filename: str) -> FileResponse:
    path = pdf_service.pdf_path(comic_id, filename)
    return FileResponse(path, media_type="application/pdf", filename=filename)


@router.get("/export/success", response_class=HTMLResponse)
def export_success(request: Request, comic_id: str, file: str):
    pdf_service.pdf_path(comic_id, file)  # 404 if the file doesn't exist
    comic = comic_service.load_comic(comic_id)
    return templates.TemplateResponse(
        request,
        "success.html",
        {
            "comic_id": comic_id,
            "title": comic.title,
            "panel_count": len(comic.panels),
            "filename": file,
            "download_url": f"/api/export/download/{comic_id}/{file}",
        },
    )
