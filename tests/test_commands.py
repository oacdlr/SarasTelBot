import asyncio
import os
import time
from collections import Counter
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from saras.bot import telegram_bot
from saras.bot.status import format_status
from saras.core.memory import ConversationMemory
from saras.core.modes import discovery, execution, quiz
from saras.integrations.gemini_client import GeminiHealth, GroundedAnswer
from saras.integrations.obsidian_vault import count_notes, recent_notes, write_note

from tests.test_modes import BODY_EN, EXTRACTION_EN


def _update(text, chat_id=42):
    """A minimal Update stand-in: enough for command handlers (allowed-check patched out)."""
    message = MagicMock()
    message.text = text
    message.reply_text = AsyncMock()
    return SimpleNamespace(message=message, effective_chat=SimpleNamespace(id=chat_id))


def _files(root) -> list[str]:
    return [os.path.join(d, f) for d, _, names in os.walk(root) for f in names]


@patch("saras.core.modes.discovery.ask", new_callable=AsyncMock,
       return_value=EXTRACTION_EN)
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


@patch("saras.bot.telegram_bot.is_allowed", return_value=True)
def test_notes_command_lists_recent_notes(mock_allowed, vault):
    write_note("Discovery", "A", "x", [])
    write_note("Execution", "B", "x", [])
    update = _update("/notes 5")
    asyncio.run(telegram_bot.notes(update, None))
    reply = update.message.reply_text.await_args.args[0]
    assert ">A<" in reply and ">B<" in reply


@patch("saras.bot.telegram_bot.is_allowed", return_value=True)
def test_notes_command_empty_vault(mock_allowed, vault):
    update = _update("/notes")
    asyncio.run(telegram_bot.notes(update, None))
    assert "No notes saved yet" in update.message.reply_text.await_args.args[0]


@patch("saras.bot.telegram_bot.is_allowed", return_value=True)
def test_notes_command_rejects_non_numeric_argument(mock_allowed, vault):
    update = _update("/notes abc")
    asyncio.run(telegram_bot.notes(update, None))
    assert "Usage: /notes" in update.message.reply_text.await_args.args[0]


@patch("saras.bot.telegram_bot.is_allowed", return_value=True)
def test_search_command_lists_matches(mock_allowed, vault):
    write_note("Discovery", "Docker Basics", "Docker runs containers.", ["docker"])
    write_note("Discovery", "Unrelated", "Nothing to do with it.", [])
    update = _update("/search docker")
    asyncio.run(telegram_bot.search(update, None))
    reply = update.message.reply_text.await_args.args[0]
    assert ">Docker Basics<" in reply and "Unrelated" not in reply


@patch("saras.bot.telegram_bot.is_allowed", return_value=True)
def test_search_command_no_matches(mock_allowed, vault):
    update = _update("/search zzzzz")
    asyncio.run(telegram_bot.search(update, None))
    assert "No matches" in update.message.reply_text.await_args.args[0]


@patch("saras.bot.telegram_bot.is_allowed", return_value=True)
def test_search_command_requires_a_query(mock_allowed, vault):
    update = _update("/search")
    asyncio.run(telegram_bot.search(update, None))
    assert "Usage: /search" in update.message.reply_text.await_args.args[0]


@patch("saras.bot.telegram_bot.is_allowed", return_value=True)
def test_clear_command_reports_whether_it_cleared_something(mock_allowed, monkeypatch):
    monkeypatch.setattr(telegram_bot, "memory", ConversationMemory())
    telegram_bot.memory.add(42, "hola", "hola")

    update = _update("/clear")
    asyncio.run(telegram_bot.clear(update, None))
    assert "cleared" in update.message.reply_text.await_args.args[0]
    assert telegram_bot.memory.history(42) == []

    update2 = _update("/clear")
    asyncio.run(telegram_bot.clear(update2, None))
    assert "Nothing to clear" in update2.message.reply_text.await_args.args[0]


@patch("saras.bot.telegram_bot.is_allowed", return_value=True)
def test_help_command_lists_every_registered_command(mock_allowed):
    update = _update("/help")
    asyncio.run(telegram_bot.help_command(update, None))
    reply = update.message.reply_text.await_args.args[0]
    for command in telegram_bot.COMMAND_MENU:
        assert f"/{command.command}" in reply


def test_discovery_prompt_asks_for_next_steps_after_uncertainty_in_both_languages():
    for lang, heading, before in (
        ("en", "## What to learn next", "## Uncertainty and open questions"),
        ("es", "## Qué aprender después", "## Incertidumbre y preguntas abiertas"),
    ):
        prompt = discovery._system_prompt(discovery._STRINGS[lang])
        assert heading in prompt
        assert prompt.index(before) < prompt.index(heading)


def _real_update(text, edited=False):
    """A real PTB Update holding a text (or /command) message, new or edited."""
    from datetime import datetime, timezone
    from telegram import Chat, Message, MessageEntity, Update, User
    entities = ([MessageEntity(MessageEntity.BOT_COMMAND, 0, len(text.split()[0]))]
                if text.startswith("/") else None)
    message = Message(1, datetime.now(timezone.utc), Chat(42, Chat.PRIVATE),
                      from_user=User(7, "oscar", False), text=text, entities=entities)
    message.set_bot(SimpleNamespace(username="saras_bot"))  # CommandHandler reads the bot's name
    if edited:
        return Update(1, edited_message=message)
    return Update(1, message=message)


def _registered_handlers():
    app = MagicMock()
    telegram_bot.add_handlers(app)
    return [call.args[0] for call in app.add_handler.call_args_list]


def test_handlers_ignore_edited_messages():
    for text in ("/research docker", "/help", "/fix discovery", "hola, qué tal"):
        assert not any(h.check_update(_real_update(text, edited=True))
                       for h in _registered_handlers()), text


def test_handlers_still_match_new_messages():
    for text in ("/research docker", "/help", "/fix discovery", "hola, qué tal"):
        assert any(h.check_update(_real_update(text)) for h in _registered_handlers()), text
