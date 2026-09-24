"""Gemini provider: the only module that talks to the Gemini API.

Modes depend on these functions, not on the SDK, so the provider can be
swapped later without touching mode logic.
"""
import asyncio
import logging
from dataclasses import dataclass, field

from google import genai
from google.genai import errors, types

from saras import config

_client: genai.Client | None = None

LANGUAGE_RULE = (
    "Always reply in the same language as the user's message "
    "(Spanish if they wrote in Spanish, English if they wrote in English)."
)


log = logging.getLogger(__name__)


class QuotaExceeded(RuntimeError):
    """The Gemini quota for this kind of request is used up."""


@dataclass
class GroundedAnswer:
    text: str
    sources: list[str] = field(default_factory=list)  # "Title - URL"
    grounded: bool = True  # False when the answer came from the model alone


class ModelUnavailable(RuntimeError):
    """Gemini is overloaded (503) even after retrying and trying the fast model."""


BUSY_RETRY_DELAY = 3  # seconds to wait before retrying an overloaded model


def _is_quota_error(exc: Exception) -> bool:
    return isinstance(exc, errors.ClientError) and exc.code == 429


def _is_busy_error(exc: Exception) -> bool:
    return isinstance(exc, errors.ServerError) and exc.code == 503


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=config.gemini_api_key())
    return _client


async def ask(prompt: str, system: str | None = None, fast: bool = False) -> str:
    """Ask Gemini. When the model is overloaded, retry once, then use the fast model."""
    models = [config.gemini_model(), config.gemini_model(), config.gemini_fast_model()]
    if fast:
        models = [config.gemini_fast_model(), config.gemini_fast_model()]
    for attempt, model in enumerate(models):
        if attempt:
            await asyncio.sleep(BUSY_RETRY_DELAY)
        try:
            response = await _get_client().aio.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(system_instruction=system) if system else None,
            )
        except Exception as exc:
            if _is_quota_error(exc):
                raise QuotaExceeded(str(exc)) from exc
            if not _is_busy_error(exc):
                raise
            log.warning("Gemini model %s is overloaded (attempt %d)", model, attempt + 1)
            continue
        return (response.text or "").strip()
    raise ModelUnavailable("Gemini is overloaded; try again later")


async def research(prompt: str, system: str | None = None) -> GroundedAnswer:
    """Answer with Google Search grounding, falling back to the model's own knowledge.

    Search grounding needs its own Gemini quota, which free-tier keys don't have.
    Rather than failing the whole request, answer ungrounded and say so.
    """
    try:
        response = await _get_client().aio.models.generate_content(
            model=config.gemini_model(),
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=system,
                tools=[types.Tool(google_search=types.GoogleSearch())],
            ),
        )
    except Exception as exc:
        if _is_quota_error(exc):
            log.warning("Search grounding unavailable (quota); answering without sources")
        elif _is_busy_error(exc):
            log.warning("Gemini overloaded during search; answering without sources")
        else:
            raise
        return GroundedAnswer(text=await ask(prompt, system=system), grounded=False)
    sources: list[str] = []
    for candidate in response.candidates or []:
        metadata = candidate.grounding_metadata
        for chunk in (metadata.grounding_chunks or []) if metadata else []:
            web = chunk.web
            if web and web.uri:
                entry = f"{web.title or web.domain or 'Source'} - {web.uri}"
                if entry not in sources:
                    sources.append(entry)
    return GroundedAnswer(text=(response.text or "").strip(), sources=sources)


INTENT_LABELS = ("discovery", "retrieval", "execution", "chat")


async def classify_intent(message: str) -> str:
    prompt = (
        "You route messages for SARAS, a personal knowledge assistant. "
        "Classify the message with exactly one word:\n"
        "- discovery: the user wants to learn or research something new\n"
        "- retrieval: the user asks about something they learned, saved or decided before\n"
        "- execution: the user wants to plan, organize or break down a task, project or deadline\n"
        "- chat: greetings, thanks, small talk or anything else\n\n"
        f"Message: {message}\n\nLabel:"
    )
    answer = (await ask(prompt, fast=True)).lower()
    for label in INTENT_LABELS:
        if label in answer:
            return label
    return "chat"
