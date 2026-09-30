# ComicCraft

Turn your ideas into AI-powered comics.

You describe a story (prompt, character, setting, tone, art style, 3-6 panels). **Google Gemini** writes the script, narration, dialogue and per-panel image prompts. **Stable Diffusion** (Hugging Face Diffusers, run locally) paints every panel. You read the comic in the browser and export it as a PDF.

## Features

- Structured story generation with Gemini (JSON, validated with Pydantic, one automatic retry on bad output)
- Local image generation with Diffusers - no image API key or paid service
- Live progress in the browser ("Creating your story...", "Generating panel 2 of 4...") with panels appearing as they finish
- Comic-book UI: bordered panels, narration captions, speech bubbles, responsive layout
- Every "Create My Comic" click regenerates the story, image prompts **and** images (changing tone or art style is a real regeneration)
- PDF export (cover page + one page per panel) and a download page
- Clear errors for a missing API key, Gemini failures, invalid JSON, GPU out-of-memory, missing model, and bad input

## Architecture

```
Browser (HTML/CSS/vanilla JS)
   |  POST /api/comic/jobs  ->  poll GET /api/comic/jobs/{id}
   v
FastAPI (app/main.py, app/routes/)
   v
comic_service.generate_comic
   |-- gemini_service   -> Gemini API -> validated Story (Pydantic)
   |-- prompt_builder   -> Stable Diffusion prompt per panel (style tags + character + scene + tone)
   |-- image_service    -> Diffusers pipeline (lazy singleton) -> static/generated/<comic_id>/panel_N.png
   v
static/generated/<comic_id>/comic.json      (the saved comic)
   v
pdf_service -> layout_builder.py (geometry) -> exporters.py (fpdf2) -> comic_YYYYMMDD_HHMMSS.pdf
```

```
app/
  main.py, config.py, errors.py, templating.py
  routes/      comic.py (generate / jobs / get), export.py (export / download / success page)
  services/    gemini_service.py, image_service.py, comic_service.py, pdf_service.py
  models/      schemas.py
  utils/       prompt_builder.py
  templates/   index.html, success.html
static/        css/style.css, js/app.js, generated/ (output, git-ignored)
layout_builder.py, exporters.py   PDF layout + rendering
tests/
```

Gemini is only ever called from the Python backend; the API key never reaches the browser.

## Requirements

- **Python 3.10+** (developed on 3.13)
- A **Gemini API key** (free tier available at <https://aistudio.google.com/apikey>)
- ~5 GB free disk for the image model and ~3 GB more for PyTorch with CUDA
- **Recommended:** an NVIDIA GPU with 6 GB+ VRAM (see [GPU requirements](#gpu-requirements))

## Installation

```bash
python -m venv venv
```

Activate it:

- Windows (PowerShell / cmd): `venv\Scripts\activate`
- macOS / Linux: `source venv/bin/activate`

### GPU setup (NVIDIA, Windows/Linux) - do this first

A plain `pip install torch` on Windows installs a **CPU-only** build. For an NVIDIA GPU, install the CUDA build *before* the other requirements:

```bash
pip install torch --index-url https://download.pytorch.org/whl/cu126
```

(Pick the CUDA version matching your driver at <https://pytorch.org/get-started/locally/>.) Verify:

```bash
python -c "import torch; print(torch.cuda.is_available())"   # should print True
```

macOS (Apple Silicon) and CPU-only users can skip this step; the default `torch` wheel is fine (MPS is auto-detected on Apple Silicon).

### Everything else

```bash
pip install -r requirements.txt
```

## Gemini API key setup

1. Create a key at <https://aistudio.google.com/apikey>.
2. Copy `.env.example` to `.env` (a blank `.env` already exists if you cloned this project fresh from the build).
3. Put the key in `.env`:

   ```
   GEMINI_API_KEY=your_key_here
   GEMINI_MODEL=gemini-flash-latest
   ```

`.env` is git-ignored. If the key is missing, the app still starts, shows a warning banner, and generation returns a clear "GEMINI_API_KEY is not set" error - it never fakes a story.

`GEMINI_MODEL` is configurable in one place. Model names change over time; if you get a "model not found" error, pick a current model from <https://ai.google.dev/gemini-api/docs/models>.

## Hugging Face model setup

The default image model is **`Lykon/dreamshaper-8`**: a Stable Diffusion 1.5 fine-tune that handles illustrated / anime / comic styles well, uses the permissive CreativeML OpenRAIL-M licence, is public (**no Hugging Face account or token needed**) and fits comfortably in 6 GB of VRAM.

The weights (~2-4 GB) download automatically the first time you generate a comic and are cached in `~/.cache/huggingface`. Set `IMAGE_MODEL` to change model - any Diffusers text-to-image repo id or local folder works, for example:

| Goal | `IMAGE_MODEL` |
|---|---|
| Default (illustrated, 6 GB GPU) | `Lykon/dreamshaper-8` |
| Plain Stable Diffusion 1.5 | `stable-diffusion-v1-5/stable-diffusion-v1-5` |
| Faster on CPU / tiny GPUs (few steps) | a distilled SD model, with `IMAGE_STEPS=8` |
| Higher quality (needs 10 GB+ VRAM) | an SDXL-based Diffusers repo, with `IMAGE_WIDTH=1024 IMAGE_HEIGHT=768` |

Only set `HF_TOKEN` if you choose a gated/private model.

## Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `GEMINI_API_KEY` | *(required)* | Gemini key, backend only |
| `GEMINI_MODEL` | `gemini-flash-latest` | Gemini model used for stories |
| `IMAGE_MODEL` | `Lykon/dreamshaper-8` | Diffusers repo id or local path |
| `IMAGE_DEVICE` | `auto` | `auto`, `cuda`, `mps` or `cpu` |
| `IMAGE_WIDTH` / `IMAGE_HEIGHT` | `576` / `448` | Panel size (rounded to multiples of 8, 256-1024) |
| `IMAGE_STEPS` | 25 GPU / 15 CPU | Inference steps |
| `IMAGE_GUIDANCE` | `7.0` | Guidance scale |
| `IMAGE_SEED` | random | Set a number for reproducible comics (panel *n* uses seed + *n*) |
| `IMAGE_NEGATIVE_PROMPT` | built-in | Things the image model should avoid |
| `HF_TOKEN` | *(empty)* | Only for gated models |
| `PDF_FONT_PATH` | auto | Unicode `.ttf` for the PDF (auto-detects Arial / DejaVu) |

## Running the application

```bash
uvicorn app.main:app --reload
```

Open <http://127.0.0.1:8000>, fill in the form and click **Create My Comic**. The first comic is slower because the image model downloads and loads once; later panels and comics reuse the loaded model.

Tip: `--reload` restarts the server (and unloads the model) whenever code changes. For long sessions run without it.

## GPU requirements

- NVIDIA GPU with **6 GB VRAM** works at the default 576x448 (tested on an RTX 3050 Laptop 6 GB). Expect roughly a few seconds per panel.
- If you hit "GPU ran out of memory", lower `IMAGE_WIDTH` / `IMAGE_HEIGHT` (e.g. 512x384), close other GPU programs, or set `IMAGE_DEVICE=cpu`.
- Apple Silicon uses MPS automatically.

## CPU limitations

The app works without a GPU, but **Stable Diffusion on a CPU is extremely slow** - typically several minutes *per panel* (a 4-panel comic can take 10-30+ minutes). ComicCraft logs a warning and drops the default steps to 15 on CPU. For CPU testing use 3 panels, `IMAGE_WIDTH=384 IMAGE_HEIGHT=320`, `IMAGE_STEPS=10`, or swap in a smaller/distilled model via `IMAGE_MODEL`.

## PDF export

Click **Export PDF** under the comic. The PDF has a cover page (title, panel count, style, tone) and one page per panel with the panel title, the image (aspect ratio preserved), the narration and the dialogue, with long text wrapped. Files are named `comic_YYYYMMDD_HHMMSS.pdf`, stored next to the comic in `static/generated/<comic_id>/`, and offered on a "Comic exported successfully!" page with a download button. If no Unicode font is found, curly quotes and dashes are converted to plain ASCII equivalents; set `PDF_FONT_PATH` to keep non-Latin scripts.

## API endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/` | Web UI |
| GET | `/health` | `{"status": "ok", ...}` plus Gemini/image-model status (does not load the model) |
| POST | `/api/comic/generate` | Generate synchronously; returns `{comic_id, title, panels, ...}` |
| POST | `/api/comic/jobs` | Start generation in the background (used by the UI) -> `{job_id, ...}` |
| GET | `/api/comic/jobs/{job_id}` | Progress, finished panels and (when done) the comic. `job_id` == `comic_id` |
| GET | `/api/comic/{comic_id}` | Fetch a saved comic |
| POST | `/api/comic/export` | `{"comic_id": "..."}` -> builds the PDF, returns download/success URLs |
| GET | `/api/export/download/{comic_id}/{filename}` | Download the PDF |
| GET | `/export/success?comic_id=...&file=...` | Export success page |

Example request body for `/api/comic/generate`:

```json
{
  "prompt": "A brave fox exploring an enchanted forest",
  "character_name": "Finn",
  "setting": "Enchanted forest",
  "tone": "dramatic",
  "art_style": "anime",
  "panel_count": 4
}
```

Errors are returned as `{"detail": "<message>", "code": "<error_code>"}`. Interactive docs: <http://127.0.0.1:8000/docs>.

## Tests

```bash
pytest
```

The tests cover input validation, Gemini JSON parsing (plain, fenced, invalid, wrong panel count), schema validation, prompt building, layout + PDF generation, the health endpoint, the frontend, and the full generate -> export -> download flow. The automated tests replace only the two external edges (the Gemini network call and the Diffusers pipeline) with stand-ins; the application itself ships with no fake AI output.

## Troubleshooting

| Problem | Fix |
|---|---|
| "GEMINI_API_KEY is not set" | Add the key to `.env`, restart uvicorn |
| "Gemini rejected the API key" | Check for typos / extra quotes in `.env`; create a new key |
| "Gemini model '...' was not found" | Set `GEMINI_MODEL` to a model your key can use |
| "rate limit or quota exceeded" | Wait, or use a different model/key |
| "Gemini did not return valid JSON" | Retry; ComicCraft already retries once. Try another `GEMINI_MODEL` |
| `torch.cuda.is_available()` is `False` | You have the CPU wheel: reinstall with the CUDA index URL above |
| "GPU ran out of memory" | Lower `IMAGE_WIDTH`/`IMAGE_HEIGHT`, close other GPU apps |
| "Could not load image model" | Check `IMAGE_MODEL` spelling and internet access (first run downloads it) |
| Generation is very slow | You are on CPU - see [CPU limitations](#cpu-limitations) |
| Panels are all black | The model's safety checker flagged the image; regenerate or choose another `IMAGE_MODEL` |
| Characters look different between panels | Expected with Stable Diffusion; Gemini repeats a fixed appearance description in every prompt to help, but consistency is approximate |
| Changes to `.env` do nothing | Restart uvicorn - `.env` is read at startup |
