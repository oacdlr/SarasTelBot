"""Discovery Mode (Learn): research a topic and store it as a Vault note."""
from saras.core.modes.base import ModeResult
from saras.integrations.gemini_client import LANGUAGE_RULE, ask, research
from saras.integrations.obsidian_vault import note_title, search_notes, write_note

SYSTEM = (
    "You are SARAS in Discovery Mode. Research the user's question and turn it into "
    "clear, well-structured knowledge: start with the core idea, then build up the "
    "details, use Markdown headings and short paragraphs, and match the depth the "
    "user asks for. Be accurate and say when something is uncertain. " + LANGUAGE_RULE
)


async def _make_title(message: str) -> str:
    return await ask(
        "Write a short, specific title (max 8 words) for a knowledge note answering this "
        "request, in the same language as the request. Reply with the title only, "
        f"no quotes or punctuation at the end.\n\nRequest: {message}",
        fast=True,
    )


async def run(message: str, previous: list[ModeResult] | None = None) -> ModeResult:
    answer = await research(message, system=SYSTEM)
    title = (await _make_title(message)).strip().strip('"\'') or message

    body = answer.text
    related = [n for n in search_notes(f"{title} {message}", limit=5) if n.score >= 3]
    if related:
        body += "\n\n## Related\n" + "\n".join(f"- [[{n.title}]]" for n in related)
    if answer.sources:
        body += "\n\n## Sources\n" + "\n".join(f"- {s}" for s in answer.sources)
    elif not answer.grounded:
        body += (
            "\n\n> [!warning] Sin fuentes web / No web sources\n"
            "> Written from the model's own knowledge: web search was unavailable "
            "(Gemini search-grounding quota). Verify before relying on details."
        )

    tags = ["discovery"] if answer.grounded else ["discovery", "unverified"]
    path = write_note("Discovery", title, body, tags=tags, sources=answer.sources)
    reply = f"{answer.text}\n\n📚 Saved to Vault: [[{note_title(path)}]]"
    if not answer.grounded:
        reply += "\n⚠️ Sin búsqueda web (cuota de Gemini) — respuesta sin fuentes."
    return ModeResult(reply=reply, note_path=path)
