"""Execution Mode (Act): turn an objective into a checklist plan in the Vault."""
import asyncio
from datetime import date

from saras.core.modes.base import ModeResult
from saras.core.persona import EXECUTION as SYSTEM
from saras.integrations.llm import ask
from saras.integrations.obsidian_vault import find_related, note_title, write_note

MAX_RESEARCH_CHARS = 8000


async def run(
    message: str, previous: list[ModeResult] | None = None, save: bool = True
) -> ModeResult:
    prompt = f"Today is {date.today().isoformat()}.\n\nObjective: {message}"
    earlier = [r for r in previous or [] if r.note_path]
    if earlier:
        research_text = "\n\n".join(r.full_text() for r in earlier)
        prompt += f"\n\nResearch already done for this objective:\n{research_text[:MAX_RESEARCH_CHARS]}"

    if not save:
        plan = await ask(prompt, system=SYSTEM)
        return ModeResult(reply=f"{plan}\n\n🚫 Not saved to Vault (/nosave)")
    # The title only needs the objective, so it's asked alongside the plan.
    plan, title = await asyncio.gather(
        ask(prompt, system=SYSTEM),
        ask(
            "Write a short title (max 6 words) for a project plan with this objective, in the "
            f"same language. Reply with the title only.\n\nObjective: {message}",
            fast=True,
        ),
    )

    links = [note_title(r.note_path) for r in earlier]
    links += [n.title for n in find_related(message, exclude=set(links)) if n.title not in links]
    body = plan
    if links:
        body += "\n\n## Related knowledge\n" + "\n".join(f"- [[{t}]]" for t in links)

    path = write_note("Execution", title.strip().strip('"\'') or message, body, tags=["execution"],
                      note_type="execution")
    return ModeResult(reply=f"{plan}\n\n✅ Plan saved to Vault: [[{note_title(path)}]]", note_path=path)
