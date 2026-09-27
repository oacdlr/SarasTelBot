"""The Obsidian Vault: SARAS's persistent, human-readable memory.

Notes are plain Markdown files with YAML frontmatter, so the vault stays
usable without SARAS.
"""
import os
import re
import time
import unicodedata
from dataclasses import dataclass
from datetime import date

from saras import config

# Characters Windows (and Obsidian links) can't use in filenames.
_INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*#^\[\]\x00-\x1f]')
_MAX_TITLE_LENGTH = 80

STOPWORDS = {
    # English
    "a", "an", "the", "and", "or", "but", "of", "to", "in", "on", "at", "for", "with",
    "about", "from", "by", "is", "are", "was", "were", "be", "been", "it", "this", "that",
    "what", "which", "who", "how", "why", "when", "where", "do", "does", "did", "i", "me",
    "my", "you", "your", "we", "our", "can", "could", "should", "would", "will", "have",
    "has", "had", "learn", "learned", "last", "month", "week", "time", "tell", "remind",
    "know", "anything", "something", "any", "some", "there", "again",
    # Spanish
    "el", "la", "los", "las", "un", "una", "unos", "unas", "y", "o", "pero", "de", "del",
    "a", "al", "en", "con", "por", "para", "sobre", "que", "qué", "es", "son", "fue",
    "era", "ser", "lo", "le", "les", "se", "mi", "mis", "me", "yo", "tu", "tus", "te",
    "su", "sus", "como", "cómo", "cuando", "cuándo", "donde", "dónde", "cual", "cuál",
    "quien", "quién", "aprendí", "aprendi", "sé", "algo", "sabes", "dime", "recuérdame",
    "recuerdame", "mes", "semana", "pasado", "pasada", "vez", "esto", "eso", "este", "esta",
}


@dataclass
class Note:
    path: str
    title: str
    body: str
    tags: list[str]
    score: float = 0.0


def safe_title(title: str) -> str:
    """Turn arbitrary text into a filename-safe note title."""
    cleaned = _INVALID_FILENAME_CHARS.sub(" ", title)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    if len(cleaned) > _MAX_TITLE_LENGTH:
        cleaned = cleaned[:_MAX_TITLE_LENGTH].rsplit(" ", 1)[0].strip(" .")
    return cleaned or "Untitled"


def _yaml_str(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _reserve_path(folder: str, title: str) -> tuple[str, str]:
    """Pick a free path for a new note, without creating the file yet."""
    title = safe_title(title)
    folder_path = os.path.join(config.obsidian_vault_path(), folder)
    os.makedirs(folder_path, exist_ok=True)

    path = os.path.join(folder_path, f"{title}.md")
    counter = 2
    while os.path.exists(path):
        path = os.path.join(folder_path, f"{title} ({counter}).md")
        counter += 1
    return path, title


def write_note(
    folder: str,
    title: str,
    body: str,
    tags: list[str],
    sources: list[str] | None = None,
) -> str:
    """Write a new note and return its path. Never overwrites an existing note."""
    path, title = _reserve_path(folder, title)

    lines = [
        "---",
        f"title: {_yaml_str(title)}",
        f"date: {date.today().isoformat()}",
        f"tags: [{', '.join(tags)}]",
    ]
    if sources:
        lines.append("sources:")
        lines.extend(f"  - {_yaml_str(s)}" for s in sources)
    lines += ["---", "", ""]

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + body.strip() + "\n")
    return path


def write_raw_note(folder: str, title: str, content: str) -> str:
    """Write a note whose full Markdown (frontmatter + body) is already assembled.

    Like write_note, this never overwrites an existing note.
    """
    path, _ = _reserve_path(folder, title)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content.strip() + "\n")
    return path


def note_title(path: str) -> str:
    """The name Obsidian uses for [[wikilinks]]: the filename without .md."""
    return os.path.splitext(os.path.basename(path))[0]


def find_concept(name: str) -> str | None:
    """Find an existing Concepts/ note by filename or alias (case/accent-insensitive)."""
    concepts_dir = os.path.join(config.obsidian_vault_path(), "Concepts")
    target = _strip_accents(name.strip().lower())
    if not target or not os.path.isdir(concepts_dir):
        return None

    entries = sorted(e for e in os.listdir(concepts_dir) if e.endswith(".md"))
    for entry in entries:
        path = os.path.join(concepts_dir, entry)
        if _strip_accents(note_title(path).lower()) == target:
            return path

    for entry in entries:
        path = os.path.join(concepts_dir, entry)
        try:
            _, aliases, _ = _parse(path)
        except (OSError, UnicodeDecodeError):
            continue
        if any(_strip_accents(a.lower()) == target for a in aliases):
            return path
    return None


def append_under_heading(path: str, heading: str, line: str) -> None:
    """Append `line` as a new bullet under a Markdown heading, unless it's already there."""
    with open(path, encoding="utf-8") as f:
        text = f.read()
    if line in text.splitlines():
        return

    lines = text.split("\n")
    heading_line = f"## {heading}"
    try:
        idx = next(i for i, l in enumerate(lines) if l.strip() == heading_line)
    except StopIteration:
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"\n{heading_line}\n{line}\n")
        return

    insert_at = idx + 1
    while insert_at < len(lines) and lines[insert_at].lstrip().startswith("- "):
        insert_at += 1
    lines.insert(insert_at, line)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def upsert_concept(
    name: str,
    aliases: list[str],
    content: str,
    backlink_heading: str,
    backlink_line: str,
) -> str:
    """Create a Concepts/ note from `content`, or, if one already matches `name`/`aliases`,
    leave it untouched except for appending `backlink_line` under `backlink_heading` (once).
    Returns the note's path either way.
    """
    existing = find_concept(name)
    if existing is None:
        for alias in aliases:
            existing = find_concept(alias)
            if existing:
                break
    if existing:
        append_under_heading(existing, backlink_heading, backlink_line)
        return existing
    return write_raw_note("Concepts", name, content)


def _strip_accents(text: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn"
    )


def keywords(text: str) -> list[str]:
    words = re.findall(r"[\w\-+#.]+", text.lower())
    seen = []
    for w in (w.strip(".") for w in words):
        if len(w) > 1 and w not in STOPWORDS and w not in seen:
            seen.append(w)
    return seen


def _parse(path: str) -> tuple[list[str], list[str], str]:
    with open(path, encoding="utf-8") as f:
        content = f.read()
    tags: list[str] = []
    aliases: list[str] = []
    body = content
    if content.startswith("---"):
        end = content.find("\n---", 3)
        if end != -1:
            frontmatter, body = content[3:end], content[end + 4 :]
            match = re.search(r"^tags:\s*\[(.*)\]", frontmatter, re.MULTILINE)
            if match:
                tags = [t.strip().lower() for t in match.group(1).split(",") if t.strip()]
            match = re.search(r"^aliases:\s*\[(.*)\]", frontmatter, re.MULTILINE)
            if match:
                aliases = [
                    a.strip().strip('"\'') for a in match.group(1).split(",") if a.strip()
                ]
    return tags, aliases, body


def search_notes(query: str, limit: int = 5) -> list[Note]:
    """Keyword search over the vault, ranked by title/tag/body hits plus recency."""
    terms = [_strip_accents(k) for k in keywords(query)]
    vault = config.obsidian_vault_path()
    if not terms or not os.path.isdir(vault):
        return []

    now = time.time()
    results: list[Note] = []
    for root, dirs, files in os.walk(vault):
        dirs[:] = [d for d in dirs if not d.startswith(".")]  # skip .obsidian, .trash
        for name in files:
            if not name.endswith(".md"):
                continue
            path = os.path.join(root, name)
            try:
                tags, aliases, body = _parse(path)
            except (OSError, UnicodeDecodeError):
                continue
            title = note_title(path)
            title_n = _strip_accents(title.lower())
            body_n = _strip_accents(body.lower())
            tags_n = [_strip_accents(t) for t in tags]
            aliases_n = [_strip_accents(a.lower()) for a in aliases]

            score = 0.0
            for term in terms:
                if term in title_n or any(term in a for a in aliases_n):
                    score += 3
                if term in tags_n:
                    score += 2
                if term in body_n:
                    score += 1 + min(body_n.count(term), 5) * 0.1
            if score == 0:
                continue
            age_days = (now - os.path.getmtime(path)) / 86400
            score += max(0.0, 1.0 - age_days / 365)  # small boost for recent notes
            results.append(Note(path=path, title=title, body=body.strip(), tags=tags, score=score))

    results.sort(key=lambda n: n.score, reverse=True)
    return results[:limit]
