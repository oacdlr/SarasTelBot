"""The "📋 Planear esto" / "🔍 Más detalle" / "🗑️ No guardar" buttons under a Discovery answer."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from saras.bot import telegram_bot
from saras.core.memory import ConversationMemory
from saras.core.modes.base import ModeResult


def _update(text, chat_id=42):
    """Update stand-in whose status message supports edit_text, like the real send_reply path."""
    status_msg = MagicMock()
    status_msg.edit_text = AsyncMock()
    message = MagicMock()
    message.text = text
    message.chat.send_action = AsyncMock()
    message.reply_text = AsyncMock(return_value=status_msg)
    update = SimpleNamespace(message=message, effective_chat=SimpleNamespace(id=chat_id))
    return update, status_msg


def _callback(action, answer_id, chat_id=42, user_id=7):
    query = MagicMock()
    query.data = f"ans:{action}:{answer_id}"
    query.message.chat_id = chat_id
    query.message.chat.send_action = AsyncMock()  # for respond()'s typing indicator, if reached
    query.message.reply_text = AsyncMock()
    query.answer = AsyncMock()
    query.edit_message_reply_markup = AsyncMock()
    update = SimpleNamespace(callback_query=query, effective_user=SimpleNamespace(id=user_id))
    return update, query


@patch("saras.bot.telegram_bot.is_allowed", return_value=True)
@patch("saras.bot.telegram_bot.route", new_callable=AsyncMock, return_value=[("discovery", "Explain Docker")])
@patch("saras.bot.telegram_bot.make_standalone", new_callable=AsyncMock, return_value="Explain Docker")
def test_respond_attaches_keyboard_after_a_saved_discovery_answer(mock_standalone, mock_route, mock_allowed, monkeypatch):
    monkeypatch.setattr(telegram_bot, "memory", ConversationMemory())
    monkeypatch.setattr(telegram_bot, "pending_answers", {})
    discovery_result = ModeResult(reply="Docker packages apps.", note_path="/vault/Discovery/Docker.md")
    monkeypatch.setitem(telegram_bot.MODES, "discovery", AsyncMock(return_value=discovery_result))

    update, status_msg = _update("Explain Docker")
    asyncio.run(telegram_bot.respond(update, "Explain Docker"))

    markup = status_msg.edit_text.await_args.kwargs["reply_markup"]
    assert [b.text for row in markup.inline_keyboard for b in row] == [
        "📋 Planear esto", "🔍 Más detalle", "🗑️ No guardar",
    ]
    pending = telegram_bot.pending_answers[42]
    assert pending.result is discovery_result
    assert pending.topic == "Explain Docker"
    callback_data = markup.inline_keyboard[0][0].callback_data
    assert callback_data == f"ans:plan:{pending.answer_id}"


@patch("saras.bot.telegram_bot.is_allowed", return_value=True)
@patch("saras.bot.telegram_bot.route", new_callable=AsyncMock, return_value=[("discovery", "Explain Docker")])
@patch("saras.bot.telegram_bot.make_standalone", new_callable=AsyncMock, return_value="Explain Docker")
def test_respond_no_keyboard_when_not_saved(mock_standalone, mock_route, mock_allowed, monkeypatch):
    monkeypatch.setattr(telegram_bot, "memory", ConversationMemory())
    monkeypatch.setattr(telegram_bot, "pending_answers", {})
    monkeypatch.setitem(
        telegram_bot.MODES, "discovery",
        AsyncMock(return_value=ModeResult(reply="Not saved.", note_path=None)),
    )

    update, status_msg = _update("Explain Docker")
    asyncio.run(telegram_bot.respond(update, "Explain Docker", save=False))

    assert status_msg.edit_text.await_args.kwargs["reply_markup"] is None
    assert telegram_bot.pending_answers == {}


@patch("saras.bot.telegram_bot.is_allowed", return_value=True)
@patch("saras.bot.telegram_bot.route", new_callable=AsyncMock, return_value=[("retrieval", "What is Docker?")])
@patch("saras.bot.telegram_bot.make_standalone", new_callable=AsyncMock, return_value="What is Docker?")
def test_respond_no_keyboard_for_non_discovery_answers(mock_standalone, mock_route, mock_allowed, monkeypatch):
    monkeypatch.setattr(telegram_bot, "memory", ConversationMemory())
    monkeypatch.setattr(telegram_bot, "pending_answers", {})
    monkeypatch.setitem(
        telegram_bot.MODES, "retrieval",
        AsyncMock(return_value=ModeResult(reply="From your notes.", note_path=None)),
    )

    update, _status_msg = _update("What is Docker?")
    asyncio.run(telegram_bot.respond(update, "What is Docker?"))

    # retrieval never saves, so no status message either; the reply goes straight to reply_text.
    assert update.message.reply_text.await_args.kwargs["reply_markup"] is None
    assert telegram_bot.pending_answers == {}


@patch("saras.bot.telegram_bot.is_allowed", return_value=True)
def test_drop_button_deletes_the_note_and_clears_pending(mock_allowed, monkeypatch):
    pending = telegram_bot.PendingAnswer(
        result=ModeResult(reply="x", note_path="/vault/Discovery/Docker.md"), topic="Docker", answer_id=5,
    )
    monkeypatch.setattr(telegram_bot, "pending_answers", {42: pending})
    mock_delete = MagicMock(return_value=True)
    monkeypatch.setattr(telegram_bot, "delete_note", mock_delete)

    update, query = _callback("drop", 5)
    asyncio.run(telegram_bot.answer_button(update, None))

    mock_delete.assert_called_once_with("/vault/Discovery/Docker.md")
    query.edit_message_reply_markup.assert_awaited_once_with(reply_markup=None)
    query.message.reply_text.assert_awaited_once()
    assert telegram_bot.pending_answers == {}


@patch("saras.bot.telegram_bot.is_allowed", return_value=True)
def test_plan_button_runs_execution_with_the_saved_answer_as_context(mock_allowed, monkeypatch):
    monkeypatch.setattr(telegram_bot, "memory", ConversationMemory())
    discovery_result = ModeResult(reply="Docker packages apps.", note_path="/vault/Discovery/Docker.md")
    pending = telegram_bot.PendingAnswer(result=discovery_result, topic="Explain Docker", answer_id=9)
    monkeypatch.setattr(telegram_bot, "pending_answers", {42: pending})
    seen = {}

    async def _execution(text, previous=None, save=True):
        seen["text"], seen["previous"] = text, list(previous or [])  # snapshot: `previous` mutates after return
        return ModeResult(reply="Checklist.", note_path="/vault/Execution/Plan.md")

    monkeypatch.setitem(telegram_bot.MODES, "execution", _execution)

    update, query = _callback("plan", 9)
    asyncio.run(telegram_bot.answer_button(update, None))

    assert seen["text"] == "Explain Docker"
    assert seen["previous"] == [discovery_result]
    query.message.reply_text.assert_awaited()  # the plan's reply was sent
    assert telegram_bot.pending_answers == {}


@patch("saras.bot.telegram_bot.is_allowed", return_value=True)
def test_detail_button_runs_detail_mode_with_the_saved_answer_as_context(mock_allowed, monkeypatch):
    monkeypatch.setattr(telegram_bot, "memory", ConversationMemory())
    discovery_result = ModeResult(reply="Docker packages apps.", note_path="/vault/Discovery/Docker.md")
    pending = telegram_bot.PendingAnswer(result=discovery_result, topic="Explain Docker", answer_id=3)
    monkeypatch.setattr(telegram_bot, "pending_answers", {42: pending})
    seen = {}

    async def _detail(text, previous=None, save=True):
        seen["text"], seen["previous"] = text, list(previous or [])  # snapshot: `previous` mutates after return
        return ModeResult(reply="Deeper explanation.")

    monkeypatch.setitem(telegram_bot.MODES, "detail", _detail)

    update, query = _callback("detail", 3)
    asyncio.run(telegram_bot.answer_button(update, None))

    assert seen["text"] == "Explain Docker"
    assert seen["previous"] == [discovery_result]


@patch("saras.bot.telegram_bot.is_allowed", return_value=True)
def test_stale_button_is_rejected_without_acting(mock_allowed, monkeypatch):
    pending = telegram_bot.PendingAnswer(
        result=ModeResult(reply="x", note_path="/vault/Discovery/Docker.md"), topic="Docker", answer_id=5,
    )
    monkeypatch.setattr(telegram_bot, "pending_answers", {42: pending})
    mock_delete = MagicMock()
    monkeypatch.setattr(telegram_bot, "delete_note", mock_delete)

    update, query = _callback("drop", 999)  # stale/mismatched answer_id
    asyncio.run(telegram_bot.answer_button(update, None))

    mock_delete.assert_not_called()
    query.answer.assert_awaited_once()
    assert query.answer.await_args.kwargs.get("show_alert") is True
    assert telegram_bot.pending_answers == {42: pending}  # untouched


@patch("saras.bot.telegram_bot.is_allowed", return_value=False)
def test_unauthorized_user_is_ignored(mock_allowed, monkeypatch):
    pending = telegram_bot.PendingAnswer(
        result=ModeResult(reply="x", note_path="/vault/Discovery/Docker.md"), topic="Docker", answer_id=5,
    )
    monkeypatch.setattr(telegram_bot, "pending_answers", {42: pending})
    mock_delete = MagicMock()
    monkeypatch.setattr(telegram_bot, "delete_note", mock_delete)

    update, query = _callback("drop", 5, user_id=666)
    asyncio.run(telegram_bot.answer_button(update, None))

    mock_delete.assert_not_called()
    assert telegram_bot.pending_answers == {42: pending}
