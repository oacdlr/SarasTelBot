"""Execution Mode (Act): turn an objective into a checklist plan in the Vault."""
from datetime import date

from saras.core.modes.base import ModeResult
from saras.core.persona import EXECUTION as SYSTEM
from saras.integrations.gemini_client import ask
from saras.integrations.obsidian_vault import find_related, note_title, write_note



async def run(
    message: str, previous: list[ModeResult] | None = None, save: bool = True
) -> ModeResult:
    prompt = f"Today is {date.today().isoformat()}.\n\nObjective: {message}"
    earlier = [r for r in previous or [] if r.note_path]
    if earlier:
        research_text = "\n\n".join(r.reply for r in earlier)
        prompt += f"\n\nResearch already done for this objective:\n{research_text[:8000]}"

    plan = await ask(prompt, system=SYSTEM)
    if not save:
        return ModeResult(reply=f"{plan}\n\n🚫 Not saved to Vault (/nosave)")
    title = await ask(
        "Write a short title (max 6 words) for a project plan with this objective, in the "
        f"same language. Reply with the title only.\n\nObjective: {message}",
        fast=True,
    )

    links = [note_title(r.note_path) for r in earlier]
    links += [n.title for n in find_related(message, exclude=set(links)) if n.title not in links]
    body = plan
    if links:
        body += "\n\n## Related knowledge\n" + "\n".join(f"- [[{t}]]" for t in links)

    path = write_note("Execution", title.strip().strip('"\'') or message, body, tags=["execution"])
    return ModeResult(reply=f"{plan}\n\n✅ Plan saved to Vault: [[{note_title(path)}]]", note_path=path)
