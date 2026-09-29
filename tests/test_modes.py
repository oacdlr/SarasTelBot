import asyncio
import json
import os
import pytest
from unittest.mock import AsyncMock, patch

from saras.bot.telegram_bot import split_message
from saras.core.modes import detail, discovery, execution, retrieval
from saras.core.modes.base import ModeResult
from saras.integrations.gemini_client import GroundedAnswer
from saras.integrations.obsidian_vault import find_concept, upsert_concept, write_note, write_raw_note

BODY_ES = (
    "## Prerrequisitos\n"
    "- [[Contenedores]]: para entender el aislamiento de procesos\n\n"
    "## Conceptos clave\n"
    "- [[Container]]: unidad ligera que empaqueta una app [1]\n\n"
    "## 1. Fundamentos\n"
    "Docker es una plataforma de contenedores [1].\n\n"
    "## 2. Cómo funciona\n"
    "Usa namespaces y cgroups del kernel de Linux [1].\n\n"
    "## 3. En la práctica / estado actual\n"
    "Se usa ampliamente en CI/CD y microservicios [1].\n\n"
    "## Incertidumbre y preguntas abiertas\n"
    "- No está claro el rendimiento exacto frente a VMs ligeras.\n"
)

EXTRACTION_ES = json.dumps({
    "short_answer": "Docker empaqueta apps en contenedores ligeros y portables.",
    "confidence": "high",
    "tags": ["docker", "containers"],
    "concepts": [{
        "name": "Container",
        "aliases": ["Contenedor"],
        "definition": "Una unidad ligera y aislada que empaqueta una app y sus dependencias.",
        "why_it_matters": "Hace que los despliegues sean reproducibles.",
        "example": "Ejecutar `docker run nginx`.",
    }],
})

BODY_EN = (
    "## Prerequisites\n"
    "- [[Containers]]: to understand process isolation\n\n"
    "## Key concepts\n"
    "- [[Container]]: lightweight unit that packages an app [1]\n\n"
    "## 1. Foundations\n"
    "Docker is a container platform [1].\n\n"
    "## 2. How it works\n"
    "It uses Linux kernel namespaces and cgroups [1].\n\n"
    "## 3. In practice / current state\n"
    "Widely used in CI/CD and microservices [1].\n\n"
    "## Uncertainty and open questions\n"
    "- Exact performance versus lightweight VMs is unclear.\n"
)

EXTRACTION_EN = json.dumps({
    "short_answer": "Docker packages apps into lightweight, portable containers.",
    "confidence": "medium",
    "tags": ["docker", "containers"],
    "concepts": [{
        "name": "Container",
        "aliases": ["Docker container"],
        "definition": "A lightweight, isolated unit that packages an app and its dependencies.",
        "why_it_matters": "It makes deployments reproducible.",
        "example": "Running `docker run nginx`.",
    }],
})


@patch("saras.core.modes.discovery.ask", new_callable=AsyncMock,
       side_effect=["Docker Basics", EXTRACTION_ES])
@patch("saras.core.modes.discovery.research", new_callable=AsyncMock,
       return_value=GroundedAnswer(BODY_ES, ["Docs - https://docs.docker.com"]))
def test_discovery_writes_hub_note_es(mock_research, mock_ask, vault):
    result = asyncio.run(discovery.run("Explícame qué es Docker"))
    assert os.path.dirname(result.note_path) == str(vault / "Discovery")
    content = open(result.note_path, encoding="utf-8").read()

    assert 'type: discovery' in content
    assert 'question: "Explícame qué es Docker"' in content
    assert 'status: aprendiendo' in content
    assert 'confidence: alta' in content
    assert 'tags: [discovery, docker, containers]' in content
    assert 'concepts: ["[[Container]]"]' in content
    assert 'sources: ["https://docs.docker.com"]' in content
    assert "> [!question] Pregunta" in content
    assert "> [!summary] Respuesta corta" in content
    assert "## Prerrequisitos" in content
    assert "## Conceptos clave" in content
    assert "## 1. Fundamentos" in content
    assert "## 2. Cómo funciona" in content
    assert "## 3. En la práctica / estado actual" in content
    assert "## Fuentes" in content
    assert "1. [Docs](https://docs.docker.com)" in content

    assert result.reply.startswith("Docker empaqueta apps en contenedores ligeros y portables.")
    assert "[[Container]]" in result.reply
    assert "📚 Saved to Vault: [[Docker Basics]]" in result.reply


@patch("saras.core.modes.discovery.ask", new_callable=AsyncMock,
       side_effect=["Docker Basics", EXTRACTION_EN])
@patch("saras.core.modes.discovery.research", new_callable=AsyncMock,
       return_value=GroundedAnswer(BODY_EN, ["Docs - https://docs.docker.com"]))
def test_discovery_writes_hub_note_en(mock_research, mock_ask, vault):
    result = asyncio.run(discovery.run("Explain what Docker is"))
    content = open(result.note_path, encoding="utf-8").read()

    assert 'type: discovery' in content
    assert 'status: learning' in content
    assert 'confidence: medium' in content
    assert "> [!question] Question" in content
    assert "> [!summary] Short answer" in content
    assert "## Prerequisites" in content
    assert "## Key concepts" in content
    assert "## 1. Foundations" in content
    assert "## Sources" in content

    assert result.reply.startswith("Docker packages apps into lightweight, portable containers.")
    assert "📚 Saved to Vault: [[Docker Basics]]" in result.reply


@patch("saras.core.modes.discovery.ask", new_callable=AsyncMock,
       side_effect=["Docker Basics", EXTRACTION_ES])
@patch("saras.core.modes.discovery.research", new_callable=AsyncMock,
       return_value=GroundedAnswer(BODY_ES, ["Docs - https://docs.docker.com"]))
def test_discovery_creates_concept_note(mock_research, mock_ask, vault):
    asyncio.run(discovery.run("Explícame qué es Docker"))
    concept_path = vault / "Concepts" / "Container.md"
    assert concept_path.exists()
    content = concept_path.read_text(encoding="utf-8")
    assert "type: concept" in content
    assert 'aliases: ["Contenedor"]' in content
    assert "## Aparece en" in content
    assert "- [[Docker Basics]]" in content
    assert "## Fuentes" in content
    assert "https://docs.docker.com" in content


def test_upsert_concept_does_not_overwrite_and_appends_backlink_once(vault):
    original = (
        "---\n"
        'title: "Container"\n'
        "type: concept\n"
        "date: 2026-01-01\n"
        "status: entendido\n"
        'aliases: ["Contenedor"]\n'
        "tags: [concept, docker]\n"
        "---\n\n"
        "**Container** is a hand-written definition that must survive.\n\n"
        "## Why it matters\nBecause I wrote it myself.\n\n"
        "## Appears in\n- [[Old Note]]\n"
    )
    existing_path = write_raw_note("Concepts", "Container", original)

    new_content = '---\ntitle: "Container"\n---\n\nThis should never be written.\n'
    path = upsert_concept(
        name="Container", aliases=["Contenedor"], content=new_content,
        backlink_heading="Appears in", backlink_line="- [[New Hub]]",
    )
    assert path == existing_path
    text = open(path, encoding="utf-8").read()
    assert "hand-written definition that must survive" in text
    assert "This should never be written" not in text
    assert "- [[Old Note]]" in text
    assert text.count("- [[New Hub]]") == 1

    upsert_concept(
        name="Container", aliases=["Contenedor"], content=new_content,
        backlink_heading="Appears in", backlink_line="- [[New Hub]]",
    )
    text = open(path, encoding="utf-8").read()
    assert text.count("- [[New Hub]]") == 1


def test_find_concept_matches_alias_and_accent_case_differences(vault):
    content = (
        "---\n"
        'title: "Aprendizaje Automático"\n'
        "type: concept\n"
        "date: 2026-01-01\n"
        "status: aprendiendo\n"
        'aliases: ["Machine Learning", "ML"]\n'
        "tags: [concept]\n"
        "---\n\n"
        "**Aprendizaje Automático** es ...\n"
    )
    path = write_raw_note("Concepts", "Aprendizaje Automático", content)

    assert find_concept("aprendizaje automatico") == path
    assert find_concept("machine learning") == path
    assert find_concept("ML") == path
    assert find_concept("Nonexistent") is None


def test_parse_extraction_falls_back_on_bad_json():
    data = discovery._parse_extraction("not json at all", "## 1. Foundations\nDocker is great.\n")
    assert data["confidence"] == "medium"
    assert data["concepts"] == []
    assert data["tags"] == []
    assert data["short_answer"]


@patch("saras.core.modes.discovery.ask", new_callable=AsyncMock,
       side_effect=["Docker Basics", "not valid json"])
@patch("saras.core.modes.discovery.research", new_callable=AsyncMock,
       return_value=GroundedAnswer("## 1. Foundations\nDocker packages apps.\n",
                                    ["Docs - https://docs.docker.com"]))
def test_discovery_handles_bad_extraction_json(mock_research, mock_ask, vault):
    result = asyncio.run(discovery.run("Explain Docker"))
    content = open(result.note_path, encoding="utf-8").read()
    assert "confidence: medium" in content
    assert "## 1. Foundations" in content
    assert result.reply


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


@patch("saras.core.modes.execution.ask", new_callable=AsyncMock,
       side_effect=["- [ ] Ship it", "Kubernetes Rollout"])
def test_execution_related_knowledge_uses_strict_matching(mock_ask, vault):
    write_note("Discovery", "Kubernetes basics", "Pods and nodes.", ["kubernetes"])
    write_note("Discovery", "Cooking pasta", "Mention of kubernetes rollout in passing.", ["food"])
    result = asyncio.run(execution.run("Help me plan my Kubernetes rollout"))
    content = open(result.note_path, encoding="utf-8").read()
    assert "## Related knowledge" in content
    assert "[[Kubernetes basics]]" in content
    assert "[[Cooking pasta]]" not in content


@patch("saras.core.modes.detail.ask", new_callable=AsyncMock, return_value="Deeper answer.")
def test_detail_expands_with_earlier_reply_as_context(mock_ask):
    result = asyncio.run(detail.run("Docker", previous=[ModeResult(reply="Docker runs containers.")]))
    assert result.reply == "Deeper answer."
    assert result.note_path is None
    prompt = mock_ask.await_args.args[0]
    assert "Topic: Docker" in prompt and "Docker runs containers." in prompt


@patch("saras.core.modes.detail.ask", new_callable=AsyncMock, return_value="Deeper answer.")
def test_detail_without_previous_still_asks(mock_ask):
    result = asyncio.run(detail.run("Docker"))
    assert result.reply == "Deeper answer."
    assert mock_ask.await_args.args[0] == "Topic: Docker"


def test_split_message_respects_telegram_limit():
    text = "\n\n".join("x" * 1000 for _ in range(10))
    chunks = split_message(text)
    assert len(chunks) > 1 and all(len(c) <= 4096 for c in chunks)
    assert "".join(chunks).replace("\n", "") == text.replace("\n", "")


@patch("saras.core.modes.discovery.ask", new_callable=AsyncMock,
       side_effect=["Docker Basics", EXTRACTION_EN])
@patch("saras.core.modes.discovery.research", new_callable=AsyncMock,
       return_value=GroundedAnswer("## 1. Foundations\nExplanation without search.\n",
                                    [], grounded=False))
def test_discovery_marks_note_when_search_was_unavailable(mock_research, mock_ask, vault):
    result = asyncio.run(discovery.run("Explain Docker"))
    content = open(result.note_path, encoding="utf-8").read()
    assert "unverified" in content
    assert "confidence: low" in content
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


@patch("saras.core.modes.discovery.ask", new_callable=AsyncMock,
       side_effect=["Docker Basics", EXTRACTION_EN])
@patch("saras.core.modes.discovery.research", new_callable=AsyncMock,
       return_value=GroundedAnswer(BODY_EN, ["Docs - https://docs.docker.com"]))
def test_discovery_related_uses_topic_not_generic_words(mock_research, mock_ask, vault):
    write_note("Discovery", "Docker Networking", "Bridge networks.", ["docker"])
    write_note("Discovery", "Overview of Roman Roads", "Via Appia.", ["history"])
    result = asyncio.run(discovery.run("Explain what Docker is, an overview"))
    content = open(result.note_path, encoding="utf-8").read()
    assert "## Related\n- [[Docker Networking]]" in content
    assert "Roman Roads" not in content


def test_ask_fast_falls_back_to_main_model_when_fast_is_overloaded(monkeypatch):
    from google.genai import errors
    from saras.integrations import gemini_client

    calls = []

    class FakeModels:
        async def generate_content(self, model, **kwargs):
            calls.append(model)
            if model == "fast-model":
                raise errors.ServerError(503, {"error": {"message": "high demand"}})
            return type("Response", (), {"text": "Main answer."})()

    class FakeClient:
        aio = type("aio", (), {"models": FakeModels()})()

    monkeypatch.setattr(gemini_client, "_get_client", lambda: FakeClient())
    monkeypatch.setattr(gemini_client, "BUSY_RETRY_DELAY", 0)
    monkeypatch.setattr(gemini_client.config, "gemini_model", lambda: "main-model")
    monkeypatch.setattr(gemini_client.config, "gemini_fast_model", lambda: "fast-model")
    assert asyncio.run(gemini_client.ask("hi", fast=True)) == "Main answer."
    assert calls == ["fast-model", "fast-model", "main-model"]
