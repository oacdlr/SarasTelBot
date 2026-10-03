"""Intent router: decides which SARAS mode(s) handle a message.

Keyword rules first (cheap, predictable), Gemini classification as fallback.
"""
import logging
import re

from saras.core.memory import Turn, format_history
from saras.integrations.gemini_client import ModelUnavailable, QuotaExceeded, ask

log = logging.getLogger(__name__)

INTENT_LABELS = ("discovery", "retrieval", "execution", "quiz", "chat")

# Checked in this order: the most specific intent wins.
KEYWORDS = {
    "quiz": [
        "quiz me", "quiz", "test me", "examíname", "examiname", "hazme un quiz",
        "ponme a prueba",
    ],
    "retrieval": [
        "what did i", "what have i", "remind me", "last time", "did i save", "my notes",
        "qué aprendí", "que aprendi", "qué sé", "recuérdame", "recuerdame", "la última vez",
        "mis notas", "qué había", "que habia", "qué guardé", "que guarde",
    ],
    "execution": [
        "help me plan", "break down", "organize", "organise", "due date", "is due", "due by",
        "deadline", "to-do", "todo list", "schedule",
        "ayúdame a planear", "ayudame a planear", "ayúdame a organizar", "ayudame a organizar",
        "organiza", "planea", "mi entrega", "fecha de entrega", "entregar", "fecha límite",
        "fecha limite", "mis pendientes", "tengo pendientes",
    ],
    "discovery": [
        "research", "explain", "what is", "what are", "how does", "how do", "teach me",
        "investiga", "explica", "explícame", "explicame", "qué es", "que es", "qué son",
        "cómo funciona", "como funciona", "enséñame", "enseñame","quiero aprender sobre",
    ],
}

# "Research X and then help me plan Y" → Discovery followed by Execution.
_CHAIN_SPLIT = re.compile(
    r"\b(?:and then|then|after that|y luego|luego|y después|y despues|después|despues)\b",
    re.IGNORECASE,
)


def match_keywords(message: str) -> str | None:
    lowered = message.lower()
    for mode, words in KEYWORDS.items():
        if any(re.search(rf"(?<!\w){re.escape(w)}(?!\w)", lowered) for w in words):
            return mode
    return None


async def classify_intent(message: str, history: str = "") -> str:
    """Pick a mode label; `history` is recent conversation, so follow-ups keep their mode."""
    prompt = (
        "You route messages for SARAS, a personal knowledge assistant. "
        "Classify the message with exactly one word:\n"
        "- discovery: the user wants to learn or research something new\n"
        "- retrieval: the user asks about something they learned, saved or decided before\n"
        "- execution: the user wants to plan, organize or break down a task, project or deadline\n"
        "- quiz: the user wants to be tested or quizzed on what they learned\n"
        "- chat: greetings, thanks, small talk or anything else\n\n"
    )
    if history:
        prompt += (
            f"{history}\n\nA short follow-up (e.g. \"and in Python?\") continues what the "
            "conversation was doing.\n\n"
        )
    prompt += f"Message: {message}\n\nLabel:"
    answer = (await ask(prompt, fast=True)).lower()
    for label in INTENT_LABELS:
        if label in answer:
            return label
    return "chat"


async def route(message: str, history: list[Turn] | None = None) -> list[tuple[str, str]]:
    """Return an ordered list of (mode, text) steps to run."""
    parts = [p.strip(" ,.;") for p in _CHAIN_SPLIT.split(message, maxsplit=1)]
    if len(parts) == 2 and all(parts):
        first, second = match_keywords(parts[0]), match_keywords(parts[1])
        if first == "discovery" and second == "execution":
            return [("discovery", parts[0]), ("execution", message)]

    mode = match_keywords(message) or await classify_intent(message, format_history(history))
    return [(mode, message)]


async def make_standalone(message: str, history: list[Turn] | None) -> str:
    """Rewrite a follow-up ("¿y en Python?") as a self-contained request.

    Modes search the Vault and the web with the message alone, so they need the
    subject spelled out. Falls back to the original message if the rewrite fails.
    """
    if not history:
        return message
    prompt = (
        "Rewrite the user's latest message as a standalone request, using the conversation "
        "only to fill in what it refers to (\"it\", \"and in Python?\", \"the second one\"). "
        "Keep the same language, intent and level of detail; add nothing else. If the "
        "message already makes sense on its own, return it unchanged. Reply with the "
        f"rewritten message only.\n\n{format_history(history)}\n\n"
        f"Latest message: {message}\n\nStandalone message:"
    )
    try:
        rewritten = (await ask(prompt, fast=True)).strip().strip('"\'')
    except (ModelUnavailable, QuotaExceeded):
        log.warning("Could not resolve follow-up; using the message as written")
        return message
    return rewritten or message
