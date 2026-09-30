"""Story generation with the Google Gemini API."""
from __future__ import annotations

import json
import logging
import re
import time

from pydantic import ValidationError

from app.config import get_settings
from app.errors import ConfigurationError, GeminiError, InvalidStoryError
from app.models.schemas import ComicRequest, Story
from app.utils.prompt_builder import SYSTEM_INSTRUCTION, build_story_prompt

log = logging.getLogger("comiccraft.gemini")

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)
MAX_ATTEMPTS = 2  # one retry when Gemini returns unusable JSON
TRANSIENT_BACKOFF = (3, 8)  # seconds to wait before retrying 500/503 (overloaded) responses


def extract_json(text: str) -> dict:
    """Pull a JSON object out of Gemini's reply, tolerating Markdown fences and stray prose."""
    if not text or not text.strip():
        raise InvalidStoryError("Gemini returned an empty response.")
    candidates = [text.strip()]
    candidates += [m.strip() for m in _FENCE_RE.findall(text)]
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        candidates.append(text[start : end + 1])
    for candidate in candidates:
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            return data
    raise InvalidStoryError("Gemini did not return valid JSON.")


def parse_story(text: str, expected_panels: int) -> Story:
    """Extract, validate and normalise a story. Raises InvalidStoryError on any problem."""
    data = extract_json(text)
    try:
        story = Story.model_validate(data)
    except ValidationError as exc:
        first = exc.errors()[0]
        loc = ".".join(str(p) for p in first["loc"])
        raise InvalidStoryError(f"Gemini's story had an invalid structure ({loc}: {first['msg']}).") from exc
    if len(story.panels) < expected_panels:
        raise InvalidStoryError(
            f"Gemini returned {len(story.panels)} panels but {expected_panels} were requested."
        )
    story.panels = story.panels[:expected_panels]
    for i, panel in enumerate(story.panels, start=1):  # enforce clean 1..N numbering
        panel.panel_number = i
    return story


def _scrub(message: str, api_key: str) -> str:
    return message.replace(api_key, "***") if api_key else message


def _call_gemini(prompt: str) -> str:
    settings = get_settings()
    if not settings.gemini_configured:
        raise ConfigurationError(
            "GEMINI_API_KEY is not set. Add your key to the .env file (see .env.example) and restart the server."
        )
    try:
        from google import genai
        from google.genai import errors as genai_errors
        from google.genai import types
    except ImportError as exc:  # pragma: no cover
        raise ConfigurationError(
            "The 'google-genai' package is not installed. Run: pip install -r requirements.txt"
        ) from exc

    try:
        client = genai.Client(api_key=settings.gemini_api_key)
        response = client.models.generate_content(
            model=settings.gemini_model,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTION,
                response_mime_type="application/json",
                temperature=0.9,
            ),
        )
        return response.text or ""
    except genai_errors.APIError as exc:
        code = getattr(exc, "code", None)
        detail = _scrub(str(getattr(exc, "message", "") or exc), settings.gemini_api_key)
        log.warning("Gemini API error %s: %s", code, detail)
        if code in (400, 401, 403) and "key" in detail.lower():
            raise ConfigurationError("Gemini rejected the API key. Check GEMINI_API_KEY in your .env file.") from exc
        if code == 404:
            raise ConfigurationError(
                f"Gemini model '{settings.gemini_model}' was not found. Check GEMINI_MODEL in your .env file."
            ) from exc
        if code in (500, 503, 504):
            raise GeminiError(
                "Gemini is temporarily overloaded. Wait a minute and try again.", transient=True
            ) from exc
        if code == 429:
            raise GeminiError("Gemini rate limit or quota exceeded. Wait a moment and try again.") from exc
        raise GeminiError(f"The Gemini API returned an error ({code}): {detail[:300]}") from exc
    except Exception as exc:  # network errors, timeouts, blocked responses
        log.exception("Unexpected Gemini failure")
        raise GeminiError(f"Could not reach Gemini: {_scrub(str(exc), settings.gemini_api_key)[:300]}") from exc


def _call_with_backoff(prompt: str) -> str:
    for delay in (*TRANSIENT_BACKOFF, None):
        try:
            return _call_gemini(prompt)
        except GeminiError as exc:
            if not exc.transient or delay is None:
                raise
            log.warning("Gemini temporarily unavailable; retrying in %ss", delay)
            time.sleep(delay)
    raise AssertionError("unreachable")


def generate_story(req: ComicRequest) -> Story:
    prompt = build_story_prompt(req)
    last_error: InvalidStoryError | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        raw = _call_with_backoff(prompt)
        try:
            return parse_story(raw, req.panel_count)
        except InvalidStoryError as exc:
            last_error = exc
            log.warning("Attempt %d: unusable Gemini output: %s", attempt, exc.message)
    assert last_error is not None
    raise last_error
