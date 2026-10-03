"""Short-term conversation memory: the last few exchanges per chat.

Kept in RAM only: a conversation is forgotten after IDLE_TIMEOUT without a
message, and everything is lost when the bot restarts. Long-term memory is the Vault.
"""
import time
from collections import deque
from dataclasses import dataclass
from typing import Callable

MAX_TURNS = 5  # one turn = a user message and SARAS's reply
IDLE_TIMEOUT = 45 * 60  # seconds of silence before the conversation is forgotten
MAX_REPLY_CHARS = 1500  # stored per reply, so a long plan doesn't flood later prompts


@dataclass(frozen=True)
class Turn:
    user: str
    assistant: str


@dataclass
class _Chat:
    turns: deque[Turn]
    last_active: float


class ConversationMemory:
    def __init__(
        self,
        max_turns: int = MAX_TURNS,
        idle_timeout: float = IDLE_TIMEOUT,
        clock: Callable[[], float] = time.monotonic,
    ):
        self._max_turns = max_turns
        self._idle_timeout = idle_timeout
        self._clock = clock
        self._chats: dict[int, _Chat] = {}

    def history(self, chat_id: int) -> list[Turn]:
        """Recent turns, oldest first; empty if the chat is new or went idle."""
        chat = self._live_chat(chat_id)
        return list(chat.turns) if chat else []

    def add(self, chat_id: int, user: str, assistant: str) -> None:
        chat = self._live_chat(chat_id)
        if chat is None:
            chat = self._chats[chat_id] = _Chat(deque(maxlen=self._max_turns), 0.0)
        chat.turns.append(Turn(user, assistant[:MAX_REPLY_CHARS]))
        chat.last_active = self._clock()

    def drop_last(self, chat_id: int) -> bool:
        """Forget chat_id's most recent turn. Returns whether there was one to forget."""
        chat = self._live_chat(chat_id)
        if not chat or not chat.turns:
            return False
        chat.turns.pop()
        return True

    def clear(self, chat_id: int) -> bool:
        """Forget chat_id's remembered turns. Returns whether there was anything to forget."""
        return self._chats.pop(chat_id, None) is not None

    def _live_chat(self, chat_id: int) -> _Chat | None:
        chat = self._chats.get(chat_id)
        if chat and self._clock() - chat.last_active > self._idle_timeout:
            del self._chats[chat_id]
            return None
        return chat


def format_history(turns: list[Turn] | None) -> str:
    """Render turns as a prompt block; empty string when there is nothing to show."""
    if not turns:
        return ""
    lines = ["Recent conversation (oldest first):"]
    for turn in turns:
        lines += [f"User: {turn.user}", f"SARAS: {turn.assistant}"]
    return "\n".join(lines)
