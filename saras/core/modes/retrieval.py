"""Retrieval Mode (Remember): answer from the Vault instead of re-researching."""
from saras.core.modes.base import ModeResult
from saras.core.persona import RETRIEVAL as SYSTEM
from saras.integrations.gemini_client import ask
from saras.integrations.obsidian_vault import search_notes

MIN_SCORE = 2.0  # below this a match is too weak to answer from
MAX_NOTE_CHARS = 6000


NOT_FOUND = (
    "I don't have anything on that in the Vault yet. Want me to research it? "
    "/ No tengo nada sobre eso en el Vault todavía. ¿Quieres que lo investigue?"
)


async def run(
    message: str, previous: list[ModeResult] | None = None, save: bool = True
) -> ModeResult:  # never writes, so `save` is unused
    notes = [n for n in search_notes(message, limit=5) if n.score >= MIN_SCORE]
    if not notes:
        return ModeResult(reply=NOT_FOUND)

    context = "\n\n".join(
        f"=== [[{n.title}]] (tags: {', '.join(n.tags) or 'none'}) ===\n{n.body[:MAX_NOTE_CHARS]}"
        for n in notes
    )
    answer = await ask(f"User's notes:\n\n{context}\n\nQuestion: {message}", system=SYSTEM)
    return ModeResult(reply=answer)
