"""Quiz Mode (Check): test understanding of saved notes. Quizzes go in their own Vault folder."""
import re

from saras.core.modes.base import ModeResult
from saras.core.persona import QUIZ
from saras.integrations.gemini_client import ask
from saras.integrations.obsidian_vault import note_title, search_notes, write_note

MIN_SCORE = 2.0
MAX_NOTE_CHARS = 5000

_TOPIC_NOISE = re.compile(
    r"\b(quiz me( on| about)?|quiz|test me( on| about)?|on|about|"
    r"examíname( sobre| de)?|examiname( sobre| de)?|hazme un quiz( sobre| de)?|"
    r"ponme a prueba( sobre| de)?|sobre|de)\b",
    re.IGNORECASE,
)

NOT_FOUND = (
    "Nothing in the Vault to quiz you on yet. Research the topic first? "
    "/ No hay nada en el Vault para examinarte todavía. ¿Investigamos primero?"
)


async def run(
    message: str, previous: list[ModeResult] | None = None, save: bool = True
) -> ModeResult:
    topic = _TOPIC_NOISE.sub(" ", message).strip(" ?.!,") or message
    notes = [
        n
        for n in search_notes(topic, limit=4)
        if n.score >= MIN_SCORE and not n.path.replace("\\", "/").split("/")[-2] == "Quizzes"
    ]
    if not notes:
        return ModeResult(reply=NOT_FOUND)

    context = "\n\n".join(f"=== [[{n.title}]] ===\n{n.body[:MAX_NOTE_CHARS]}" for n in notes)
    quiz = await ask(f"User's notes:\n\n{context}\n\nTopic: {topic}", system=QUIZ)

    if not save:  # nothing to keep the answers in, so show the whole quiz
        return ModeResult(reply=f"{quiz.strip()}\n\n🚫 Not saved to Vault (/nosave)")

    links = "\n".join(f"- [[{n.title}]]" for n in notes)
    path = write_note(
        "Quizzes",
        f"Quiz - {topic}",
        f"{quiz.strip()}\n\n## Source notes\n{links}",
        tags=["quiz"],
    )
    # Show only the questions in chat; answers stay in the note so the user can try first.
    questions = re.split(r"^##\s*(?:Answers|Respuestas)\b", quiz, flags=re.MULTILINE | re.IGNORECASE)[0]
    reply = f"{questions.strip()}\n\n📝 Answers saved to Vault: [[{note_title(path)}]]"
    return ModeResult(reply=reply, note_path=path)
