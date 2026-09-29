import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from saras.bot import telegram_bot
from saras.core.memory import IDLE_TIMEOUT, MAX_REPLY_CHARS, ConversationMemory, Turn, format_history
from saras.core.modes import chat
from saras.core.modes.base import ModeResult
from saras.core.router import make_standalone, route
from saras.integrations.gemini_client import QuotaExceeded

HISTORY = [Turn("Explícame qué es RAG", "RAG combina búsqueda con generación.")]


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def test_keeps_only_the_last_five_turns():
    memory = ConversationMemory()
    for i in range(7):
        memory.add(1, f"q{i}", f"a{i}")
    assert [t.user for t in memory.history(1)] == ["q2", "q3", "q4", "q5", "q6"]


def test_chats_are_independent():
    memory = ConversationMemory()
    memory.add(1, "hola", "hola")
    assert memory.history(2) == []


def test_forgets_after_45_minutes_of_silence():
    clock = FakeClock()
    memory = ConversationMemory(clock=clock)
    memory.add(1, "q", "a")
    clock.now += IDLE_TIMEOUT - 1
    assert len(memory.history(1)) == 1  # still within the window
    clock.now += 2
    assert memory.history(1) == []


def test_activity_extends_the_window():
    clock = FakeClock()
    memory = ConversationMemory(clock=clock)
    memory.add(1, "q1", "a1")
    clock.now += IDLE_TIMEOUT - 60
    memory.add(1, "q2", "a2")
    clock.now += IDLE_TIMEOUT - 60
    assert [t.user for t in memory.history(1)] == ["q1", "q2"]


def test_new_conversation_after_idle_starts_clean():
    clock = FakeClock()
    memory = ConversationMemory(clock=clock)
    memory.add(1, "old", "old")
    clock.now += IDLE_TIMEOUT + 1
    memory.add(1, "new", "new")
    assert [t.user for t in memory.history(1)] == ["new"]


def test_long_replies_are_clipped():
    memory = ConversationMemory()
    memory.add(1, "q", "x" * (MAX_REPLY_CHARS + 500))
    assert len(memory.history(1)[0].assistant) == MAX_REPLY_CHARS


def test_clear_forgets_only_the_given_chat():
    memory = ConversationMemory()
    memory.add(1, "q", "a")
    memory.add(2, "q", "a")
    assert memory.clear(1) is True
    assert memory.history(1) == []
    assert [t.user for t in memory.history(2)] == ["q"]


def test_clear_on_an_unknown_chat_reports_nothing_to_clear():
    memory = ConversationMemory()
    assert memory.clear(1) is False


def test_format_history():
    assert format_history([]) == ""
    text = format_history(HISTORY)
    assert "User: Explícame qué es RAG" in text and "SARAS: RAG combina" in text


@patch("saras.core.router.ask", new_callable=AsyncMock)
def test_make_standalone_skips_the_model_without_history(mock_ask):
    assert asyncio.run(make_standalone("¿y en Python?", [])) == "¿y en Python?"
    mock_ask.assert_not_awaited()


@patch("saras.core.router.ask", new_callable=AsyncMock, return_value='"¿Cómo se implementa RAG en Python?"')
def test_make_standalone_rewrites_follow_up(mock_ask):
    result = asyncio.run(make_standalone("¿y en Python?", HISTORY))
    assert result == "¿Cómo se implementa RAG en Python?"
    prompt = mock_ask.await_args.args[0]
    assert "Explícame qué es RAG" in prompt and "¿y en Python?" in prompt


@patch("saras.core.router.ask", new_callable=AsyncMock, side_effect=QuotaExceeded("429"))
def test_make_standalone_falls_back_to_original_on_failure(mock_ask):
    assert asyncio.run(make_standalone("¿y en Python?", HISTORY)) == "¿y en Python?"


@patch("saras.core.router.classify_intent", new_callable=AsyncMock, return_value="discovery")
def test_route_gives_the_classifier_the_history(mock_classify):
    steps = asyncio.run(route("¿y en Python?", HISTORY))
    assert steps == [("discovery", "¿y en Python?")]
    assert "Explícame qué es RAG" in mock_classify.await_args.args[1]


@patch("saras.core.modes.chat.ask", new_callable=AsyncMock, return_value="ok")
def test_chat_includes_history_in_prompt(mock_ask):
    asyncio.run(chat.run("gracias", history=HISTORY))
    prompt = mock_ask.await_args.args[0]
    assert "Explícame qué es RAG" in prompt and prompt.endswith("gracias")


def _update(text, chat_id=42):
    message = MagicMock()
    message.text = text
    message.chat.send_action = AsyncMock()
    message.reply_text = AsyncMock()
    return SimpleNamespace(
        message=message,
        effective_chat=SimpleNamespace(id=chat_id),
        effective_user=SimpleNamespace(id=7),
    )


@patch("saras.bot.telegram_bot.send_reply", new_callable=AsyncMock)
@patch("saras.bot.telegram_bot.is_allowed", return_value=True)
def test_handle_message_remembers_and_resolves_follow_ups(mock_allowed, mock_send, monkeypatch):
    monkeypatch.setattr(telegram_bot, "memory", ConversationMemory())
    retrieval = AsyncMock(return_value=ModeResult(reply="Tus notas dicen X."))
    monkeypatch.setitem(telegram_bot.MODES, "retrieval", retrieval)

    with patch("saras.bot.telegram_bot.route", new_callable=AsyncMock) as route_mock, \
         patch("saras.bot.telegram_bot.make_standalone", new_callable=AsyncMock) as standalone:
        route_mock.side_effect = [[("retrieval", "¿Qué aprendí de RAG?")], [("retrieval", "¿y de Docker?")]]
        standalone.side_effect = lambda text, history: text if not history else f"[resuelto] {text}"

        asyncio.run(telegram_bot.handle_message(_update("¿Qué aprendí de RAG?"), None))
        asyncio.run(telegram_bot.handle_message(_update("¿y de Docker?"), None))

    assert route_mock.await_args_list[0].args[1] == []  # first message: no history yet
    assert [t.user for t in route_mock.await_args_list[1].args[1]] == ["¿Qué aprendí de RAG?"]
    assert retrieval.await_args_list[1].args[0] == "[resuelto] ¿y de Docker?"
    assert [t.user for t in telegram_bot.memory.history(42)] == ["¿Qué aprendí de RAG?", "¿y de Docker?"]


@patch("saras.bot.telegram_bot.send_reply", new_callable=AsyncMock)
@patch("saras.bot.telegram_bot.is_allowed", return_value=True)
def test_handle_message_does_not_remember_failed_turns(mock_allowed, mock_send, monkeypatch):
    monkeypatch.setattr(telegram_bot, "memory", ConversationMemory())
    with patch("saras.bot.telegram_bot.route", new_callable=AsyncMock, side_effect=QuotaExceeded("429")):
        asyncio.run(telegram_bot.handle_message(_update("hola"), None))
    assert telegram_bot.memory.history(42) == []
