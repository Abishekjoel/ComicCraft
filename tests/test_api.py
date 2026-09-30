from tests.conftest import VALID_REQUEST


def test_health(client):
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert "gemini_configured" in body and "image_model" in body


def test_frontend_loads(client):
    res = client.get("/")
    assert res.status_code == 200
    for needle in ["ComicCraft", "Turn your ideas into AI-powered comics.", "Create My Comic", "panel_count"]:
        assert needle in res.text
    assert client.get("/static/js/app.js").status_code == 200
    assert client.get("/static/css/style.css").status_code == 200


def test_invalid_input_returns_readable_422(client):
    res = client.post("/api/comic/generate", json={**VALID_REQUEST, "tone": "nope", "panel_count": 9})
    assert res.status_code == 422
    assert "tone" in res.json()["detail"] and "panel_count" in res.json()["detail"]


def test_missing_gemini_key_is_reported_clearly(client, monkeypatch, generated_dir):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    res = client.post("/api/comic/generate", json=VALID_REQUEST)
    assert res.status_code == 503
    assert "GEMINI_API_KEY" in res.json()["detail"]


def test_generate_get_export_download(client, fake_pipeline, generated_dir):
    res = client.post("/api/comic/generate", json=VALID_REQUEST)
    assert res.status_code == 200, res.text
    comic = res.json()
    assert len(comic["panels"]) == 3 and comic["panels"][0]["image_url"].endswith("panel_1.png")
    assert (generated_dir / comic["comic_id"] / "panel_3.png").is_file()

    assert client.get(f"/api/comic/{comic['comic_id']}").json()["title"] == comic["title"]

    exp = client.post("/api/comic/export", json={"comic_id": comic["comic_id"]})
    assert exp.status_code == 200, exp.text
    info = exp.json()
    assert info["panel_count"] == 3 and info["filename"].startswith("comic_") and info["filename"].endswith(".pdf")

    page = client.get(info["success_url"])
    assert page.status_code == 200 and "Comic exported successfully!" in page.text and info["download_url"] in page.text

    pdf = client.get(info["download_url"])
    assert pdf.status_code == 200 and pdf.headers["content-type"] == "application/pdf" and pdf.content[:4] == b"%PDF"


def test_background_job_reports_progress_and_result(client, fake_pipeline):
    job = client.post("/api/comic/jobs", json=VALID_REQUEST).json()
    status = client.get(f"/api/comic/jobs/{job['job_id']}").json()
    assert status["status"] == "done" and status["comic"]["comic_id"] == job["job_id"]
    assert len(status["panels"]) == 3


def test_job_error_is_surfaced(client, monkeypatch, generated_dir):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    job = client.post("/api/comic/jobs", json=VALID_REQUEST).json()
    status = client.get(f"/api/comic/jobs/{job['job_id']}").json()
    assert status["status"] == "error" and "GEMINI_API_KEY" in status["error"]


def test_image_failure_cleans_up(client, fake_pipeline, generated_dir, monkeypatch):
    from app.errors import ImageGenerationError
    from app.services import image_service

    def boom(*a, **k):
        raise ImageGenerationError("GPU ran out of memory")

    monkeypatch.setattr(image_service, "generate_image", boom)
    res = client.post("/api/comic/generate", json=VALID_REQUEST)
    assert res.status_code == 500 and "memory" in res.json()["detail"]
    assert list(generated_dir.iterdir()) == []


def test_unknown_and_malicious_ids(client, generated_dir):
    assert client.get("/api/comic/" + "a" * 32).status_code == 404
    assert client.get("/api/comic/not-an-id").status_code == 404
    assert client.get("/api/export/download/" + "a" * 32 + "/secret.pdf").status_code == 404
    assert client.post("/api/comic/export", json={"comic_id": "../x"}).status_code == 422
