import asyncio
from unittest.mock import AsyncMock, patch

from saras.core.router import match_keywords, route


def test_discovery_keyword():
    assert match_keywords("Explain how transformers work") == "discovery"
    assert match_keywords("Explícame cómo funciona Docker") == "discovery"


def test_retrieval_keyword():
    assert match_keywords("What did I learn about Docker last month?") == "retrieval"
    assert match_keywords("¿Qué aprendí sobre transformers?") == "retrieval"


def test_execution_keyword():
    assert match_keywords("Help me plan my ML project due Friday") == "execution"
    assert match_keywords("Organiza mi entrega del viernes") == "execution"


def test_keywords_match_whole_words_only():
    assert match_keywords("I love fondue") is None  # "due" inside a word


@patch("saras.core.router.classify_intent", new_callable=AsyncMock, return_value="chat")
def test_ambiguous_text_falls_back_to_classifier(mock_classify):
    assert asyncio.run(route("hola")) == [("chat", "hola")]
    mock_classify.assert_awaited_once()


def test_chained_discovery_then_execution():
    steps = asyncio.run(route("Research RAG architecture and then help me plan the implementation"))
    assert [mode for mode, _ in steps] == ["discovery", "execution"]
    assert steps[0][1] == "Research RAG architecture"
