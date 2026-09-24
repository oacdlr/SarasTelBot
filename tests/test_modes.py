import asyncio
import os
import pytest
from unittest.mock import AsyncMock, patch

from saras.bot.telegram_bot import split_message
from saras.core.modes import discovery, execution, retrieval
from saras.integrations.gemini_client import GroundedAnswer
from saras.integrations.obsidian_vault import write_note


@patch("saras.core.modes.discovery.ask", new_callable=AsyncMock, return_value="Docker Basics")
@patch("saras.core.modes.discovery.research", new_callable=AsyncMock,
       return_value=GroundedAnswer("A clear explanation.", ["Docs - https://docs.docker.com"]))
def test_discovery_writes_note_with_sources(mock_research, mock_ask, vault):
    result = asyncio.run(discovery.run("Explain Docker"))
    assert result.reply.startswith("A clear explanation.")
    assert os.path.dirname(result.note_path) == str(vault / "Discovery")
    content = open(result.note_path, encoding="utf-8").read()
    assert "## Sources" in content and "https://docs.docker.com" in content


@patch("saras.core.modes.retrieval.ask", new_callable=AsyncMock, return_value="From [[Docker]]: containers.")
def test_retrieval_answers_from_matching_note(mock_ask, vault):
    write_note("Discovery", "Docker", "Docker runs containers.", ["discovery"])
    result = asyncio.run(retrieval.run("What did I learn about Docker?"))
    assert result.reply == "From [[Docker]]: containers."
    assert "Docker runs containers." in mock_ask.await_args.args[0]
    assert result.note_path is None


@patch("saras.core.modes.retrieval.ask", new_callable=AsyncMock)
def test_retrieval_reports_gap_when_nothing_found(mock_ask, vault):
    result = asyncio.run(retrieval.run("What did I learn about Kubernetes?"))
    assert result.reply == retrieval.NOT_FOUND
    mock_ask.assert_not_awaited()


@patch("saras.core.modes.execution.ask", new_callable=AsyncMock,
       side_effect=["- [ ] Define scope\n- [ ] Train model", "ML Project"])
def test_execution_writes_checklist(mock_ask, vault):
    result = asyncio.run(execution.run("Help me plan my ML project due Friday"))
    content = open(result.note_path, encoding="utf-8").read()
    assert "- [ ] Define scope" in content
    assert os.path.basename(result.note_path) == "ML Project.md"


def test_split_message_respects_telegram_limit():
    text = "\n\n".join("x" * 1000 for _ in range(10))
    chunks = split_message(text)
    assert len(chunks) > 1 and all(len(c) <= 4096 for c in chunks)
    assert "".join(chunks).replace("\n", "") == text.replace("\n", "")


@patch("saras.core.modes.discovery.ask", new_callable=AsyncMock, return_value="Docker Basics")
@patch("saras.core.modes.discovery.research", new_callable=AsyncMock,
       return_value=GroundedAnswer("Explanation without search.", [], grounded=False))
def test_discovery_marks_note_when_search_was_unavailable(mock_research, mock_ask, vault):
    result = asyncio.run(discovery.run("Explain Docker"))
    content = open(result.note_path, encoding="utf-8").read()
    assert "unverified" in content
    assert "No web sources" in content
    assert "Sin búsqueda web" in result.reply


def test_research_falls_back_to_ungrounded_on_quota_error(monkeypatch):
    from google.genai import errors
    from saras.integrations import gemini_client

    quota = errors.ClientError(429, {"error": {"message": "quota"}})

    class FakeModels:
        async def generate_content(self, **kwargs):
            raise quota

    class FakeClient:
        aio = type("aio", (), {"models": FakeModels()})()

    monkeypatch.setattr(gemini_client, "_get_client", lambda: FakeClient())
    monkeypatch.setattr(gemini_client, "ask", AsyncMock(return_value="From memory."))
    answer = asyncio.run(gemini_client.research("Explain Docker"))
    assert answer.grounded is False
    assert answer.text == "From memory."
    assert answer.sources == []


def test_ask_raises_quota_exceeded(monkeypatch):
    from google.genai import errors
    from saras.integrations import gemini_client

    class FakeModels:
        async def generate_content(self, **kwargs):
            raise errors.ClientError(429, {"error": {"message": "quota"}})

    class FakeClient:
        aio = type("aio", (), {"models": FakeModels()})()

    monkeypatch.setattr(gemini_client, "_get_client", lambda: FakeClient())
    with pytest.raises(gemini_client.QuotaExceeded):
        asyncio.run(gemini_client.ask("hi"))


def test_ask_falls_back_to_fast_model_when_overloaded(monkeypatch):
    from google.genai import errors
    from saras.integrations import gemini_client

    calls = []

    class FakeModels:
        async def generate_content(self, model, **kwargs):
            calls.append(model)
            if model == "main-model":
                raise errors.ServerError(503, {"error": {"message": "high demand"}})
            return type("Response", (), {"text": "Fast answer."})()

    class FakeClient:
        aio = type("aio", (), {"models": FakeModels()})()

    monkeypatch.setattr(gemini_client, "_get_client", lambda: FakeClient())
    monkeypatch.setattr(gemini_client, "BUSY_RETRY_DELAY", 0)
    monkeypatch.setattr(gemini_client.config, "gemini_model", lambda: "main-model")
    monkeypatch.setattr(gemini_client.config, "gemini_fast_model", lambda: "fast-model")
    assert asyncio.run(gemini_client.ask("hi")) == "Fast answer."
    assert calls == ["main-model", "main-model", "fast-model"]


def test_ask_raises_model_unavailable_when_all_overloaded(monkeypatch):
    from google.genai import errors
    from saras.integrations import gemini_client

    class FakeModels:
        async def generate_content(self, **kwargs):
            raise errors.ServerError(503, {"error": {"message": "high demand"}})

    class FakeClient:
        aio = type("aio", (), {"models": FakeModels()})()

    monkeypatch.setattr(gemini_client, "_get_client", lambda: FakeClient())
    monkeypatch.setattr(gemini_client, "BUSY_RETRY_DELAY", 0)
    with pytest.raises(gemini_client.ModelUnavailable):
        asyncio.run(gemini_client.ask("hi"))
