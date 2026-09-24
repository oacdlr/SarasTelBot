"""Intent router: decides which SARAS mode(s) handle a message.

Keyword rules first (cheap, predictable), Gemini classification as fallback.
"""
import re

from saras.integrations.gemini_client import classify_intent

# Checked in this order: the most specific intent wins.
KEYWORDS = {
    "retrieval": [
        "what did i", "what have i", "remind me", "last time", "did i save", "my notes",
        "qué aprendí", "que aprendi", "qué sé", "recuérdame", "recuerdame", "la última vez",
        "mis notas", "qué había", "que habia", "qué guardé", "que guarde",
    ],
    "execution": [
        "help me plan", "break down", "organize", "organise", "due", "deadline",
        "to-do", "todo list", "schedule",
        "ayúdame a planear", "ayudame a planear", "ayúdame a organizar", "ayudame a organizar",
        "organiza", "planea", "entrega", "fecha límite", "fecha limite", "pendientes",
    ],
    "discovery": [
        "research", "explain", "what is", "what are", "how does", "how do", "teach me",
        "investiga", "explica", "explícame", "explicame", "qué es", "que es", "qué son",
        "cómo funciona", "como funciona", "enséñame", "enseñame",
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


async def route(message: str) -> list[tuple[str, str]]:
    """Return an ordered list of (mode, text) steps to run."""
    parts = [p.strip(" ,.;") for p in _CHAIN_SPLIT.split(message, maxsplit=1)]
    if len(parts) == 2 and all(parts):
        first, second = match_keywords(parts[0]), match_keywords(parts[1])
        if first == "discovery" and second == "execution":
            return [("discovery", parts[0]), ("execution", message)]

    mode = match_keywords(message) or await classify_intent(message)
    return [(mode, message)]
