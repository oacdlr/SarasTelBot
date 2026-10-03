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
    assert telegram_bot.last_routed == {42: ("hola", "chat", True, None)}

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
    monkeypatch.setattr(telegram_bot, "last_routed", {42: ("hola", "chat", True, None)})
    update, _ = _update("/fix")
    asyncio.run(telegram_bot.fix(update, None))
    markup = update.message.reply_text.await_args.kwargs["reply_markup"]
    data = [b.callback_data for row in markup.inline_keyboard for b in row]
    assert data == ["fix:discovery", "fix:retrieval", "fix:execution", "fix:quiz"]


@patch("saras.bot.telegram_bot.is_allowed", return_value=True)
def test_fix_button_logs_and_reruns_in_the_chosen_mode(mock_allowed, monkeypatch):
    monkeypatch.setattr(telegram_bot, "memory", ConversationMemory())
    monkeypatch.setattr(telegram_bot, "last_routed", {42: ("explícame RAG", "chat", True, None)})
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
    monkeypatch.setattr(telegram_bot, "last_routed", {42: ("x", "chat", True, None)})
    logged = []
    monkeypatch.setattr(telegram_bot, "log_correction", lambda *a: logged.append(a))
    update, query = _fix_callback("discovery", user_id=666)
    asyncio.run(telegram_bot.fix_button(update, None))
    assert logged == [] and telegram_bot.last_routed == {42: ("x", "chat", True, None)}


def _run_fix_redo(monkeypatch, entry, turns):
    """Press a /fix button for `entry` with `turns` already in memory; return what the redo saw."""
    monkeypatch.setattr(telegram_bot, "memory", ConversationMemory())
    for user, assistant in turns:
        telegram_bot.memory.add(42, user, assistant)
    monkeypatch.setattr(telegram_bot, "last_routed", {42: entry})
    monkeypatch.setattr(telegram_bot, "log_correction", lambda *a: None)
    monkeypatch.setattr(telegram_bot, "make_standalone", AsyncMock(side_effect=lambda text, history: text))
    seen = {}

    async def _discovery(text, previous=None, save=True):
        seen["save"] = save
        seen["history"] = [t.user for t in telegram_bot.memory.history(42)]
        return ModeResult(reply="RAG is…")

    monkeypatch.setitem(telegram_bot.MODES, "discovery", _discovery)
    update, _ = _fix_callback("discovery")
    asyncio.run(telegram_bot.fix_button(update, None))
    return seen


@patch("saras.bot.telegram_bot.is_allowed", return_value=True)
def test_fix_redo_keeps_the_nosave_flag(mock_allowed, monkeypatch):
    seen = _run_fix_redo(monkeypatch, ("explícame RAG", "chat", False, None), [("explícame RAG", "hola")])
    assert seen["save"] is False


@patch("saras.bot.telegram_bot.is_allowed", return_value=True)
def test_fix_redo_replaces_the_misrouted_turn_in_memory(mock_allowed, monkeypatch):
    seen = _run_fix_redo(monkeypatch, ("explícame RAG", "chat", True, None),
                         [("hola", "¡hola!"), ("explícame RAG", "misrouted chat reply")])
    assert seen["save"] is True
    assert seen["history"] == ["hola"]  # the misrouted turn is gone before the redo runs
    assert [(t.user, t.assistant) for t in telegram_bot.memory.history(42)] == [
        ("hola", "¡hola!"), ("explícame RAG", "RAG is…")]


@patch("saras.bot.telegram_bot.is_allowed", return_value=True)
@patch("saras.bot.telegram_bot.route", new_callable=AsyncMock, return_value=[("chat", "hola")])
@patch("saras.bot.telegram_bot.make_standalone", new_callable=AsyncMock, return_value="hola")
def test_routed_message_remembers_its_save_flag(mock_standalone, mock_route, mock_allowed, monkeypatch):
    monkeypatch.setattr(telegram_bot, "memory", ConversationMemory())
    monkeypatch.setattr(telegram_bot, "last_routed", {})
    monkeypatch.setattr(telegram_bot.chat, "run", AsyncMock(return_value=ModeResult(reply="hi")))
    update, _ = _update("hola")
    asyncio.run(telegram_bot.respond(update, "hola", save=False))
    assert telegram_bot.last_routed == {42: ("hola", "chat", False, None)}


@patch("saras.bot.telegram_bot.is_allowed", return_value=True)
@patch("saras.bot.telegram_bot.route", new_callable=AsyncMock,
       return_value=[("discovery", "RAG"), ("execution", "plan RAG")])
@patch("saras.bot.telegram_bot.make_standalone", new_callable=AsyncMock, side_effect=lambda t, h: t)
def test_later_answers_clear_a_stale_fix_target(mock_standalone, mock_route, mock_allowed, monkeypatch):
    monkeypatch.setattr(telegram_bot, "memory", ConversationMemory())
    monkeypatch.setattr(telegram_bot.discovery, "find_existing", lambda text: None)
    for mode in ("retrieval", "discovery", "execution"):
        monkeypatch.setitem(telegram_bot.MODES, mode, AsyncMock(return_value=ModeResult(reply=mode)))
    update, _ = _update("x")

    monkeypatch.setattr(telegram_bot, "last_routed", {42: ("old", "chat", True, None)})
    asyncio.run(telegram_bot.respond(update, "/recall x", force_mode="retrieval"))  # slash command
    assert telegram_bot.last_routed == {}

    monkeypatch.setattr(telegram_bot, "last_routed", {42: ("old", "chat", True, None)})
    asyncio.run(telegram_bot.respond(update, "research RAG and plan it"))  # chained request
    assert telegram_bot.last_routed == {}


@patch("saras.bot.telegram_bot.is_allowed", return_value=True)
@patch("saras.bot.telegram_bot.route", new_callable=AsyncMock, return_value=[("retrieval", "¿y en Python?")])
@patch("saras.bot.telegram_bot.make_standalone", new_callable=AsyncMock, return_value="¿Qué aprendí de RAG en Python?")
def test_routed_answer_remembers_its_rewritten_request(mock_standalone, mock_route, mock_allowed, monkeypatch):
    monkeypatch.setattr(telegram_bot, "memory", ConversationMemory())
    monkeypatch.setattr(telegram_bot, "last_routed", {})
    monkeypatch.setitem(telegram_bot.MODES, "retrieval", AsyncMock(return_value=ModeResult(reply="r")))
    update, _ = _update("¿y en Python?")
    asyncio.run(telegram_bot.respond(update, "¿y en Python?"))
    assert telegram_bot.last_routed == {
        42: ("¿y en Python?", "retrieval", True, "¿Qué aprendí de RAG en Python?")}


@patch("saras.bot.telegram_bot.is_allowed", return_value=True)
def test_fix_redo_reuses_the_rewrite_instead_of_rewriting_again(mock_allowed, monkeypatch):
    monkeypatch.setattr(telegram_bot, "memory", ConversationMemory())
    monkeypatch.setattr(telegram_bot, "last_routed",
                        {42: ("¿y en Python?", "retrieval", True, "RAG en Python")})
    logged = []
    monkeypatch.setattr(telegram_bot, "log_correction", lambda *a: logged.append(a))
    mock_standalone = AsyncMock()
    monkeypatch.setattr(telegram_bot, "make_standalone", mock_standalone)
    seen = {}

    async def _discovery(text, previous=None, save=True):
        seen["text"] = text
        return ModeResult(reply="…")

    monkeypatch.setitem(telegram_bot.MODES, "discovery", _discovery)
    monkeypatch.setattr(telegram_bot.discovery, "find_existing", lambda text: None)
    update, _ = _fix_callback("discovery")
    asyncio.run(telegram_bot.fix_button(update, None))

    mock_standalone.assert_not_awaited()
    assert seen["text"] == "RAG en Python"
    assert logged == [("¿y en Python?", "retrieval", "discovery")]  # the log keeps what was typed
