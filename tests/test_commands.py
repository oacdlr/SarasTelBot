import asyncio
import os
import time
from collections import Counter
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from saras.bot import telegram_bot
from saras.bot.status import format_status
from saras.core.modes import discovery, execution, quiz
from saras.integrations.gemini_client import GeminiHealth, GroundedAnswer
from saras.integrations.obsidian_vault import count_notes, recent_notes, write_note

from tests.test_modes import BODY_EN, EXTRACTION_EN


def _files(root) -> list[str]:
    return [os.path.join(d, f) for d, _, names in os.walk(root) for f in names]


@patch("saras.core.modes.discovery.ask", new_callable=AsyncMock,
       side_effect=["Docker Basics", EXTRACTION_EN])
@patch("saras.core.modes.discovery.research", new_callable=AsyncMock,
       return_value=GroundedAnswer(BODY_EN, ["Docs - https://docs.docker.com"]))
def test_discovery_nosave_writes_nothing(mock_research, mock_ask, vault):
    result = asyncio.run(discovery.run("Explain what Docker is", save=False))
    assert _files(vault) == []
    assert result.note_path is None
    assert result.reply.startswith("Docker packages apps")
    assert "• Container" in result.reply and "[[" not in result.reply
    assert "Not saved to Vault" in result.reply


@patch("saras.core.modes.execution.ask", new_callable=AsyncMock,
       side_effect=["- [ ] Define scope"])
def test_execution_nosave_writes_nothing(mock_ask, vault):
    result = asyncio.run(execution.run("Plan my ML project", save=False))
    assert _files(vault) == []
    assert result.note_path is None
    assert "- [ ] Define scope" in result.reply
    assert mock_ask.await_count == 1  # no title request either


@patch("saras.core.modes.quiz.ask", new_callable=AsyncMock,
       return_value="## Questions\n1. What is Docker?\n\n## Answers\n1. A container platform.")
def test_quiz_nosave_shows_answers_and_writes_no_quiz_note(mock_ask, vault):
    write_note("Discovery", "Docker", "Docker runs containers.", ["discovery"])
    result = asyncio.run(quiz.run("quiz me on Docker", save=False))
    assert not (vault / "Quizzes").exists()
    assert "A container platform." in result.reply


def test_recent_notes_newest_first_and_ignores_concepts(vault):
    old = write_note("Discovery", "Old", "x", ["discovery"])
    new = write_note("Execution", "New", "x", ["execution"])
    write_note("Concepts", "Concept", "x", ["concept"])
    os.utime(old, (1_000_000, 1_000_000))
    os.utime(new, (2_000_000, 2_000_000))
    assert recent_notes(1) == [new]
    assert recent_notes(5) == [new, old]


def test_recent_notes_empty_vault(vault):
    assert recent_notes(1) == []


def test_count_notes(vault):
    write_note("Discovery", "A", "x", [])
    write_note("Discovery", "B", "x", [])
    write_note("Concepts", "C", "x", [])
    assert count_notes() == {"Discovery": 2, "Execution": 0, "Quizzes": 0, "Concepts": 1}


def _status(health: GeminiHealth, now: float, vault_path: str = ".") -> str:
    return format_status(
        health=health, models=("main", "fast"), vault_path=vault_path,
        note_counts={"Discovery": 2}, mode_counts=Counter(discovery=3, retrieval=1),
        started=now - 7200, now=now,
    )


def test_status_reports_quota_and_search_fallback():
    now = time.time()
    text = _status(GeminiHealth(last_ok=now - 600, last_quota_error=now - 120,
                                last_search_fallback=now - 300), now)
    assert "Quota exhausted (2 min ago)" in text
    assert "Web search unavailable (5 min ago)" in text
    assert "Requests by mode: discovery 3 · retrieval 1" in text
    assert "up 2 h 0 min" in text


def test_status_all_clear_and_missing_vault():
    now = time.time()
    text = _status(GeminiHealth(last_ok=now - 10), now, vault_path="Z:/does/not/exist")
    assert "✅ No problems" in text
    assert "folder not found" in text


def test_command_args_keeps_text_after_command():
    def update(text):
        return SimpleNamespace(message=SimpleNamespace(text=text))

    assert telegram_bot.command_args(update("/research what is RAG")) == "what is RAG"
    assert telegram_bot.command_args(update("/research@SarasBot\nline one\nline two")) == "line one\nline two"
    assert telegram_bot.command_args(update("/research")) == ""


def test_nosave_flag_is_consumed_once():
    telegram_bot.nosave_next.add(42)
    assert telegram_bot._take_save_flag(42) is False
    assert telegram_bot._take_save_flag(42) is True
