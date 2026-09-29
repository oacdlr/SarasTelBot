"""/fix: correct a wrongly routed mode, and log the correction."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from saras.bot import telegram_bot
from saras.core import router_log
from saras.core.memory import ConversationMemory
from saras.core.modes.base import ModeResult
from tests.test_answer_buttons import _update


def _fix_callback(mode, chat_id=42, user_id=7):
    query = MagicMock()
    query.data = f"fix:{mode}"
    query.message.chat_id = chat_id
    query.message.chat.send_action = AsyncMock()
    query.message.reply_text = AsyncMock()
    query.answer = AsyncMock()
    query.edit_message_reply_markup = AsyncMock()
    return SimpleNamespace(callback_query=query, effective_user=SimpleNamespace(id=user_id)), query


def test_log_correction_roundtrip(tmp_path):
    path = tmp_path / "logs" / "c.jsonl"
    router_log.log_correction("explícame RAG", "chat", "discovery", path=path)
    rows = router_log.read_corrections(path)
    assert [(r["message"], r["routed"], r["corrected"]) for r in rows] == [("explícame RAG", "chat", "discovery")]
    assert router_log.read_corrections(tmp_path / "missing.jsonl") == []


@patch("saras.bot.telegram_bot.is_allowed", return_value=True)
@patch("saras.bot.telegram_bot.route", new_callable=AsyncMock, return_value=[("chat", "hola")])
@patch("saras.bot.telegram_bot.make_standalone", new_callable=AsyncMock, return_value="hola")
def test_routed_message_is_remembered_but_forced_one_is_not(mock_standalone, mock_route, mock_allowed, monkeypatch):
    monkeypatch.setattr(telegram_bot, "memory", ConversationMemory())
    monkeypatch.setattr(telegram_bot, "last_routed", {})
    monkeypatch.setattr(telegram_bot.chat, "run", AsyncMock(return_value=ModeResult(reply="hi")))
    monkeypatch.setitem(telegram_bot.MODES, "retrieval", AsyncMock(return_value=ModeResult(reply="r")))

    update, _ = _update("hola")
    asyncio.run(telegram_bot.respond(update, "hola"))
    assert telegram_bot.last_routed == {42: ("hola", "chat")}

    telegram_bot.last_routed.clear()
    asyncio.run(telegram_bot.respond(update, "hola", force_mode="retrieval"))
    assert telegram_bot.last_routed == {}


@patch("saras.bot.telegram_bot.is_allowed", return_value=True)
def test_fix_without_history_says_nothing_to_fix(mock_allowed, monkeypatch):
    monkeypatch.setattr(telegram_bot, "last_routed", {})
    update, _ = _update("/fix")
    asyncio.run(telegram_bot.fix(update, None))
    assert "Nothing to fix" in update.message.reply_text.await_args.args[0]


@patch("saras.bot.telegram_bot.is_allowed", return_value=True)
def test_fix_keyboard_excludes_the_mode_that_was_used(mock_allowed, monkeypatch):
    monkeypatch.setattr(telegram_bot, "last_routed", {42: ("hola", "chat")})
    update, _ = _update("/fix")
    asyncio.run(telegram_bot.fix(update, None))
    markup = update.message.reply_text.await_args.kwargs["reply_markup"]
    data = [b.callback_data for row in markup.inline_keyboard for b in row]
    assert data == ["fix:discovery", "fix:retrieval", "fix:execution", "fix:quiz"]


@patch("saras.bot.telegram_bot.is_allowed", return_value=True)
def test_fix_button_logs_and_reruns_in_the_chosen_mode(mock_allowed, monkeypatch):
    monkeypatch.setattr(telegram_bot, "memory", ConversationMemory())
    monkeypatch.setattr(telegram_bot, "last_routed", {42: ("explícame RAG", "chat")})
    logged = []
    monkeypatch.setattr(telegram_bot, "log_correction", lambda *a: logged.append(a))
    monkeypatch.setattr(telegram_bot, "make_standalone", AsyncMock(return_value="explícame RAG"))
    seen = {}

    async def _discovery(text, previous=None, save=True):
        seen["text"] = text
        return ModeResult(reply="RAG is…")

    monkeypatch.setitem(telegram_bot.MODES, "discovery", _discovery)

    update, query = _fix_callback("discovery")
    asyncio.run(telegram_bot.fix_button(update, None))

    assert logged == [("explícame RAG", "chat", "discovery")]
    assert seen["text"] == "explícame RAG"
    query.edit_message_reply_markup.assert_awaited_once_with(reply_markup=None)
    assert 42 not in telegram_bot.last_routed


@patch("saras.bot.telegram_bot.is_allowed", return_value=False)
def test_fix_button_ignores_unauthorized_users(mock_allowed, monkeypatch):
    monkeypatch.setattr(telegram_bot, "last_routed", {42: ("x", "chat")})
    logged = []
    monkeypatch.setattr(telegram_bot, "log_correction", lambda *a: logged.append(a))
    update, query = _fix_callback("discovery", user_id=666)
    asyncio.run(telegram_bot.fix_button(update, None))
    assert logged == [] and telegram_bot.last_routed == {42: ("x", "chat")}
