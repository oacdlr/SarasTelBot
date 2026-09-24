"""Execution Mode (Act): turn an objective into a checklist plan in the Vault."""
from datetime import date

from saras.core.modes.base import ModeResult
from saras.integrations.gemini_client import LANGUAGE_RULE, ask
from saras.integrations.obsidian_vault import note_title, search_notes, write_note

SYSTEM = (
    "You are SARAS in Execution Mode. Turn the user's objective into an actionable plan. "
    "Identify the deliverable and any deadline, then write an ordered Markdown checklist "
    "(`- [ ] task (~effort)`) grouped under short headings if useful, most important and "
    "blocking tasks first, with dates when a deadline is known. Keep it practical. "
    + LANGUAGE_RULE
)


async def run(message: str, previous: list[ModeResult] | None = None) -> ModeResult:
    prompt = f"Today is {date.today().isoformat()}.\n\nObjective: {message}"
    earlier = [r for r in previous or [] if r.note_path]
    if earlier:
        research_text = "\n\n".join(r.reply for r in earlier)
        prompt += f"\n\nResearch already done for this objective:\n{research_text[:8000]}"

    plan = await ask(prompt, system=SYSTEM)
    title = await ask(
        "Write a short title (max 6 words) for a project plan with this objective, in the "
        f"same language. Reply with the title only.\n\nObjective: {message}",
        fast=True,
    )

    links = [note_title(r.note_path) for r in earlier]
    links += [n.title for n in search_notes(message, limit=3) if n.score >= 3 and n.title not in links]
    body = plan
    if links:
        body += "\n\n## Related knowledge\n" + "\n".join(f"- [[{t}]]" for t in links)

    path = write_note("Execution", title.strip().strip('"\'') or message, body, tags=["execution"])
    return ModeResult(reply=f"{plan}\n\n✅ Plan saved to Vault: [[{note_title(path)}]]", note_path=path)
