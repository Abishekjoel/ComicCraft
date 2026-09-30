"""Panel image generation with Hugging Face Diffusers (lazy-loaded singleton pipeline)."""
from __future__ import annotations

import gc
import logging
import threading
from pathlib import Path

from app.config import get_settings
from app.errors import ImageGenerationError

log = logging.getLogger("comiccraft.image")

_lock = threading.Lock()  # one generation at a time; also guards pipeline loading
_pipeline = None
_loaded_model: str | None = None
_loaded_device: str | None = None


def detect_device(preference: str = "auto") -> str:
    """Return 'cuda', 'mps' or 'cpu'. Falls back to CPU (with a warning) if the request can't be met."""
    import torch

    preference = (preference or "auto").lower()
    has_cuda = torch.cuda.is_available()
    has_mps = getattr(torch.backends, "mps", None) is not None and torch.backends.mps.is_available()

    if preference == "cuda" and not has_cuda:
        log.warning("IMAGE_DEVICE=cuda requested but CUDA is unavailable; falling back to CPU.")
        return "cpu"
    if preference == "mps" and not has_mps:
        log.warning("IMAGE_DEVICE=mps requested but MPS is unavailable; falling back to CPU.")
        return "cpu"
    if preference in ("cuda", "mps", "cpu"):
        return preference
    if has_cuda:
        return "cuda"
    if has_mps:
        return "mps"
    return "cpu"


def status() -> dict:
    """Cheap, non-loading status for /health. Never imports torch unless it is already loaded."""
    settings = get_settings()
    return {
        "image_model": settings.image_model,
        "image_model_loaded": _pipeline is not None,
        "image_device": _loaded_device,
    }


def is_loaded() -> bool:
    return _pipeline is not None


def _load_pipeline():
    """Load the Diffusers pipeline once. Caller must hold _lock."""
    global _pipeline, _loaded_model, _loaded_device
    settings = get_settings()
    if _pipeline is not None and _loaded_model == settings.image_model:
        return _pipeline

    try:
        import torch
        from diffusers import AutoPipelineForText2Image, DPMSolverMultistepScheduler
    except ImportError as exc:
        raise ImageGenerationError(
            "Image generation dependencies are missing (torch/diffusers). Run: pip install -r requirements.txt"
        ) from exc

    device = detect_device(settings.image_device)
    if device == "cpu":
        log.warning(
            "Running Stable Diffusion on the CPU. Each image can take several minutes. "
            "A CUDA GPU (or Apple MPS) is strongly recommended."
        )
    dtype = torch.float16 if device == "cuda" else torch.float32
    kwargs = {"torch_dtype": dtype}
    if settings.hf_token:
        kwargs["token"] = settings.hf_token

    log.info("Loading image model %r on %s (first run downloads the weights)...", settings.image_model, device)
    try:
        try:
            pipe = AutoPipelineForText2Image.from_pretrained(
                settings.image_model, variant="fp16" if device == "cuda" else None, **kwargs
            )
        except (OSError, ValueError) as exc:
            if device != "cuda":
                raise
            log.info("No fp16 variant available (%s); loading default weights.", exc)
            pipe = AutoPipelineForText2Image.from_pretrained(settings.image_model, **kwargs)
    except OSError as exc:
        raise ImageGenerationError(
            f"Could not load image model '{settings.image_model}'. Check IMAGE_MODEL, your internet connection "
            f"(first run must download the weights), and that the repo needs no login (HF_TOKEN). Details: {exc}"
        ) from exc
    except Exception as exc:
        raise ImageGenerationError(f"Failed to load image model '{settings.image_model}': {exc}") from exc

    if type(pipe).__name__ == "StableDiffusionPipeline":
        try:
            pipe.scheduler = DPMSolverMultistepScheduler.from_config(pipe.scheduler.config, use_karras_sigmas=True)
        except Exception:  # keep the model's default scheduler
            log.debug("Could not switch scheduler", exc_info=True)

    try:
        pipe = pipe.to(device)
    except torch.cuda.OutOfMemoryError as exc:
        _free_memory()
        raise ImageGenerationError(
            "Not enough GPU memory to load the image model. Close other GPU programs, pick a smaller IMAGE_MODEL, "
            "or set IMAGE_DEVICE=cpu."
        ) from exc
    pipe.set_progress_bar_config(disable=True)
    if hasattr(pipe, "enable_attention_slicing"):
        pipe.enable_attention_slicing()
    if device == "cuda" and hasattr(pipe, "enable_vae_slicing"):
        pipe.enable_vae_slicing()

    _pipeline, _loaded_model, _loaded_device = pipe, settings.image_model, device
    log.info("Image model ready on %s.", device)
    return pipe


def _free_memory() -> None:
    gc.collect()
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:
        pass


def generate_image(prompt: str, seed: int, out_path: Path, negative_prompt: str | None = None) -> Path:
    """Generate one panel image, save it to out_path (PNG) and return the path."""
    settings = get_settings()
    with _lock:
        pipe = _load_pipeline()
        import torch

        steps = settings.image_steps or (15 if _loaded_device == "cpu" else 25)
        generator = torch.Generator(device="cpu").manual_seed(seed)  # CPU generator = same result on any device
        try:
            result = pipe(
                prompt=prompt,
                negative_prompt=negative_prompt if negative_prompt is not None else settings.image_negative_prompt,
                width=settings.image_width,
                height=settings.image_height,
                num_inference_steps=steps,
                guidance_scale=settings.image_guidance,
                generator=generator,
            )
        except torch.cuda.OutOfMemoryError as exc:
            _free_memory()
            raise ImageGenerationError(
                "The GPU ran out of memory. Lower IMAGE_WIDTH/IMAGE_HEIGHT in .env (e.g. 512x384) or set "
                "IMAGE_DEVICE=cpu."
            ) from exc
        except RuntimeError as exc:
            if "out of memory" in str(exc).lower():
                _free_memory()
                raise ImageGenerationError(
                    "Out of memory while generating the image. Lower IMAGE_WIDTH/IMAGE_HEIGHT in .env."
                ) from exc
            raise ImageGenerationError(f"Image generation failed: {exc}") from exc
        except Exception as exc:
            raise ImageGenerationError(f"Image generation failed: {exc}") from exc

    image = result.images[0]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(out_path, format="PNG")
    return out_path
