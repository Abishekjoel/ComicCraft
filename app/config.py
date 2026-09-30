"""Central configuration. Every setting comes from environment variables / .env."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"
GENERATED_DIR = STATIC_DIR / "generated"
TEMPLATES_DIR = BASE_DIR / "app" / "templates"

load_dotenv(BASE_DIR / ".env")

DEFAULT_GEMINI_MODEL = "gemini-flash-latest"
DEFAULT_IMAGE_MODEL = "Lykon/dreamshaper-8"  # SD 1.5 based, OpenRAIL-M, ~6 GB VRAM friendly
DEFAULT_NEGATIVE_PROMPT = (
    "text, letters, words, watermark, signature, speech bubble, caption, logo, "
    "blurry, low quality, deformed, extra fingers, extra limbs, bad anatomy, cropped"
)


def _env(name: str, default: str = "") -> str:
    value = os.getenv(name)
    return value.strip() if value and value.strip() else default


def _env_int(name: str, default: int | None) -> int | None:
    raw = _env(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        raise ValueError(f"Environment variable {name} must be an integer, got {raw!r}") from None


def _env_float(name: str, default: float) -> float:
    raw = _env(name)
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        raise ValueError(f"Environment variable {name} must be a number, got {raw!r}") from None


@dataclass(frozen=True)
class Settings:
    gemini_api_key: str
    gemini_model: str
    image_model: str
    image_device: str
    image_width: int
    image_height: int
    image_steps: int | None  # None -> chosen from the device at load time
    image_guidance: float
    image_seed: int | None  # None -> random per comic
    image_negative_prompt: str
    hf_token: str

    @property
    def gemini_configured(self) -> bool:
        return bool(self.gemini_api_key)


def get_settings() -> Settings:
    """Read settings fresh from the environment (cheap; keeps tests simple)."""

    def dim(name: str, default: int) -> int:
        value = _env_int(name, default) or default
        return max(256, min(1024, value)) // 8 * 8  # SD needs multiples of 8

    return Settings(
        gemini_api_key=_env("GEMINI_API_KEY"),
        gemini_model=_env("GEMINI_MODEL", DEFAULT_GEMINI_MODEL),
        image_model=_env("IMAGE_MODEL", DEFAULT_IMAGE_MODEL),
        image_device=_env("IMAGE_DEVICE", "auto").lower(),
        image_width=dim("IMAGE_WIDTH", 576),
        image_height=dim("IMAGE_HEIGHT", 448),
        image_steps=_env_int("IMAGE_STEPS", None),
        image_guidance=_env_float("IMAGE_GUIDANCE", 7.0),
        image_seed=_env_int("IMAGE_SEED", None),
        image_negative_prompt=_env("IMAGE_NEGATIVE_PROMPT", DEFAULT_NEGATIVE_PROMPT),
        hf_token=_env("HF_TOKEN"),
    )
