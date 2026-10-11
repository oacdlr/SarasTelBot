"""Anthropic provider: same interface as gemini_client (ask / research).

Exceptions, GroundedAnswer and the health tracker are shared with gemini_client
so the bot's error handling and /status work with either provider.
"""
import logging
import time

import anthropic

from saras import config
from saras.integrations.gemini_client import (
    GroundedAnswer,
    ModelUnavailable,
    QuotaExceeded,
    health,
)

log = logging.getLogger(__name__)

MAX_TOKENS = 16000
MAX_PAUSE_CONTINUATIONS = 3
MAX_SEARCHES = 2  # web searches per research request; each returns several sites
MAX_SOURCES = 10  # sites listed/saved as sources
_client: anthropic.AsyncAnthropic | None = None


def _get_client() -> anthropic.AsyncAnthropic:
    global _client
    if _client is None:
        _client = anthropic.AsyncAnthropic(api_key=config.anthropic_api_key())
    return _client


def _is_busy_error(exc: Exception) -> bool:
    return isinstance(exc, anthropic.APIStatusError) and exc.status_code in (500, 503, 529)


def _text_of(response) -> str:
    return "".join(block.text for block in response.content if block.type == "text").strip()


async def ask(prompt: str, system: str | None = None, fast: bool = False) -> str:
    """Ask Claude. The SDK already retries 429/5xx; if that still fails, try the other model."""
    models = [config.anthropic_model(), config.anthropic_fast_model()]
    if fast:
        models.reverse()
    for model in models:
        try:
            response = await _get_client().messages.create(
                model=model,
                max_tokens=MAX_TOKENS,
                system=system or anthropic.NOT_GIVEN,
                messages=[{"role": "user", "content": prompt}],
            )
        except anthropic.RateLimitError as exc:
            health.last_quota_error = time.time()
            raise QuotaExceeded(str(exc)) from exc
        except Exception as exc:
            if not _is_busy_error(exc):
                raise
            health.last_busy = time.time()
            log.warning("Anthropic model %s is overloaded", model)
            continue
        text = _text_of(response)
        if text:
            health.last_ok = time.time()
            return text
        log.warning("Anthropic model %s returned no text (stop_reason=%s)", model, response.stop_reason)
    raise ModelUnavailable("Anthropic is overloaded; try again later")


async def research(prompt: str, system: str | None = None) -> GroundedAnswer:
    """Answer with Anthropic web search, falling back to the model's own knowledge."""
    messages: list = [{"role": "user", "content": prompt}]
    tools = [{"type": "web_search_20260209", "name": "web_search", "max_uses": MAX_SEARCHES}]
    try:
        for _ in range(MAX_PAUSE_CONTINUATIONS + 1):
            response = await _get_client().messages.create(
                model=config.anthropic_model(),
                max_tokens=MAX_TOKENS,
                system=system or anthropic.NOT_GIVEN,
                tools=tools,
                output_config={"effort": "low"},
                messages=messages,
            )
            if response.stop_reason != "pause_turn":
                break
            messages.append({"role": "assistant", "content": response.content})
    except anthropic.RateLimitError as exc:
        log.warning("Web search unavailable (rate limit); answering without sources: %s", exc)
        return await _ungrounded(prompt, system)
    except (anthropic.BadRequestError, anthropic.PermissionDeniedError) as exc:
        log.warning("Web search unavailable; answering without sources: %s", exc)
        return await _ungrounded(prompt, system)
    except Exception as exc:
        if not _is_busy_error(exc):
            raise
        health.last_busy = time.time()
        log.warning("Anthropic overloaded during search; answering without sources")
        return await _ungrounded(prompt, system)

    sources: list[str] = []

    def add(title, url):
        if url:
            entry = f"{title or 'Source'} - {url}"
            if entry not in sources:
                sources.append(entry)

    for block in response.content:
        if block.type == "web_search_tool_result" and isinstance(block.content, list):
            for result in block.content:
                add(getattr(result, "title", None), getattr(result, "url", None))
        elif block.type == "text":
            for citation in getattr(block, "citations", None) or []:
                add(getattr(citation, "title", None), getattr(citation, "url", None))
    sources = sources[:MAX_SOURCES]
    text = _text_of(response)
    if not text:
        log.warning("Web search returned no text; answering without sources")
        return await _ungrounded(prompt, system)
    health.last_ok = time.time()
    return GroundedAnswer(text=text, sources=sources)


async def _ungrounded(prompt: str, system: str | None) -> GroundedAnswer:
    health.last_search_fallback = time.time()
    return GroundedAnswer(text=await ask(prompt, system=system), grounded=False)
