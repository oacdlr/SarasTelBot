"""The Obsidian Vault: SARAS's persistent, human-readable memory.

Notes are plain Markdown files with YAML frontmatter, so the vault stays
usable without SARAS.
"""
import math
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
    score: float = 0.0  # for ranking: relevance plus a recency boost (search_notes)
    relevance: float = 0.0  # how well the note matches, without the boost: filter on this


def safe_title(title: str) -> str:
    """Turn arbitrary text into a filename-safe note title."""
    cleaned = _INVALID_FILENAME_CHARS.sub(" ", title)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    if len(cleaned) > _MAX_TITLE_LENGTH:
        cleaned = cleaned[:_MAX_TITLE_LENGTH].rsplit(" ", 1)[0].strip(" .")
    return cleaned or "Untitled"


def yaml_str(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def bare_list(items: list[str]) -> str:
    return "[" + ", ".join(items) + "]"


def quoted_list(items: list[str]) -> str:
    return "[" + ", ".join(yaml_str(i) for i in items) + "]"


def reserve_note_path(folder: str, title: str) -> tuple[str, str]:
    """Pick a free path for a new note, without creating the file yet.

    Returns (path, safe title). The note's wikilink name is note_title(path), which
    differs from the safe title when a " (2)" suffix was needed.
    """
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
    note_type: str | None = None,
) -> str:
    """Write a new note and return its path. Never overwrites an existing note.

    `note_type` becomes the frontmatter `type:` (e.g. "execution"), like Discovery/Concept notes have.
    """
    path, title = reserve_note_path(folder, title)

    lines = ["---", f"title: {yaml_str(title)}"]
    if note_type:
        lines.append(f"type: {note_type}")
    lines += [
        f"date: {date.today().isoformat()}",
        f"tags: {bare_list(tags)}",
    ]
    if sources:
        lines.append("sources:")
        lines.extend(f"  - {yaml_str(s)}" for s in sources)
    lines += ["---", "", ""]

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + body.strip() + "\n")
    return path


def write_raw_note(folder: str, title: str, content: str, path: str | None = None) -> str:
    """Write a note whose full Markdown (frontmatter + body) is already assembled.

    Like write_note, this never overwrites an existing note. Pass `path` from
    reserve_note_path() when other notes must link to this one before it is written.
    """
    if path is None:
        path, _ = reserve_note_path(folder, title)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content.strip() + "\n")
    return path


def delete_note(path: str) -> bool:
    """Delete a note file (e.g. "🗑️ No guardar" on an answer). Returns whether it existed."""
    try:
        os.remove(path)
        return True
    except FileNotFoundError:
        return False


def note_title(path: str) -> str:
    """The name Obsidian uses for [[wikilinks]]: the filename without .md."""
    return os.path.splitext(os.path.basename(path))[0]


def _concept_key(name: str) -> str:
    return _strip_accents(name.strip().lower())


def concept_index() -> dict[str, str]:
    """{normalized filename or alias: path} for every Concepts/ note, read in one pass.

    A filename beats another note's alias for the same name; among aliases, the first
    note alphabetically wins.
    """
    concepts_dir = os.path.join(config.obsidian_vault_path(), "Concepts")
    if not os.path.isdir(concepts_dir):
        return {}
    paths = [os.path.join(concepts_dir, e) for e in sorted(os.listdir(concepts_dir)) if e.endswith(".md")]
    index: dict[str, str] = {}
    for path in paths:
        try:
            _, aliases, _ = _parse(path)
        except (OSError, UnicodeDecodeError):
            continue
        for alias in aliases:
            index.setdefault(_concept_key(alias), path)
    index.update({_concept_key(note_title(p)): p for p in reversed(paths)})  # first file wins
    return index


def find_concept(name: str, index: dict[str, str] | None = None) -> str | None:
    """Find an existing Concepts/ note by filename or alias (case/accent-insensitive)."""
    target = _concept_key(name)
    if not target:
        return None
    return (concept_index() if index is None else index).get(target)


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
    index: dict[str, str] | None = None,
) -> str:
    """Create a Concepts/ note from `content`, or, if one already matches `name`/`aliases`,
    leave it untouched except for appending `backlink_line` under `backlink_heading` (once).
    Returns the note's path either way.

    Pass `index` from concept_index() to share one scan of Concepts/ across several
    concepts; a newly created note is added to it.
    """
    if index is None:
        index = concept_index()
    keys = [k for k in map(_concept_key, [name, *aliases]) if k]
    existing = next((index[k] for k in keys if k in index), None)
    if existing:
        append_under_heading(existing, backlink_heading, backlink_line)
        return existing
    path = write_raw_note("Concepts", name, content)
    for key in [_concept_key(note_title(path)), *keys]:
        index.setdefault(key, path)
    return path


SARAS_FOLDERS = ("Discovery", "Execution", "Quizzes", "Concepts")
_NOTE_FOLDERS = ("Discovery", "Execution", "Quizzes")  # what a request produces, not concept notes


def recent_notes(limit: int = 1, folders: tuple[str, ...] = _NOTE_FOLDERS) -> list[str]:
    """Paths of the most recently written notes in `folders`, newest first."""
    vault = config.obsidian_vault_path()
    found: list[tuple[float, str]] = []
    for folder in folders:
        folder_path = os.path.join(vault, folder)
        if not os.path.isdir(folder_path):
            continue
        for name in os.listdir(folder_path):
            if name.endswith(".md"):
                path = os.path.join(folder_path, name)
                found.append((os.path.getmtime(path), path))
    found.sort(reverse=True)
    return [path for _, path in found[:limit]]


def count_notes() -> dict[str, int]:
    """Number of notes in each folder SARAS writes to."""
    vault = config.obsidian_vault_path()
    counts = {}
    for folder in SARAS_FOLDERS:
        folder_path = os.path.join(vault, folder)
        counts[folder] = (
            sum(1 for n in os.listdir(folder_path) if n.endswith(".md"))
            if os.path.isdir(folder_path)
            else 0
        )
    return counts


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


def _word_pattern(term: str) -> re.Pattern:
    # Whole-word match: a short term like "ia" or "ai" must not match inside an
    # unrelated longer word (e.g. "tecnologia", "inteligencia", "again").
    return re.compile(rf"(?<!\w){re.escape(term)}(?!\w)")


def search_notes(query: str, limit: int = 5, skip: tuple[str, ...] = ("templates",)) -> list[Note]:
    """Keyword search over the vault, ranked by title/tag/body hits plus recency.

    `skip` lists top-level folders to leave out (by default the note templates).
    """
    terms = [_strip_accents(k) for k in keywords(query)]
    vault = config.obsidian_vault_path()
    if not terms or not os.path.isdir(vault):
        return []

    patterns = [(t, _word_pattern(t)) for t in dict.fromkeys(terms)]
    now = time.time()
    results: list[Note] = []
    for path in _markdown_files(vault, skip=skip):
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
        for term, pattern in patterns:
            if pattern.search(title_n) or any(pattern.search(a) for a in aliases_n):
                score += 3
            if term in tags_n:
                score += 2
            count = len(pattern.findall(body_n))
            if count:
                score += 1 + min(count, 5) * 0.1
        if score == 0:
            continue
        age_days = (now - os.path.getmtime(path)) / 86400
        boost = max(0.0, 1.0 - age_days / 365)  # small boost for recent notes
        results.append(Note(path=path, title=title, body=body.strip(), tags=tags,
                            score=score + boost, relevance=score))

    results.sort(key=lambda n: n.score, reverse=True)
    return results[:limit]


# find_related(): stricter than search_notes(), because a wrong "Related" link sits
# in a note forever. Weights are normalised to 0-1, so a title hit on a term unique
# to one note is worth 3 and one on a term half the vault shares is worth almost 0.
RELATED_MIN_SCORE = 2.0  # summed evidence a note needs to be listed
RELATED_MIN_TERM_WEIGHT = 0.5  # and at least one shared term this specific
_RELATED_SKIP_FOLDERS = ("Execution", "Quizzes", "templates")
_RELATED_MIN_POOL = 30
# Words that fill note titles ("Guía para…", "Overview of…") without naming a topic.
# Rarity alone can't catch them: two notes sharing "guía" look like a strong match.
_TITLE_FILLER = {
    "guia", "guide", "overview", "definition", "definicion", "introduction", "introduccion",
    "understanding", "resumen", "summary", "research", "investigacion", "profunda", "deep",
    "comparativa", "comparison", "biography", "biografia", "cultural", "impact", "impacto",
    "caracteristicas", "characteristics", "esencial", "essential", "iconic", "basics",
    "fundamentos", "fundamentals", "funciona", "works", "working", "explained", "figura",
    "argumento", "commands", "configuration", "plan", "curso", "course", "tutorial",
}


def _markdown_files(vault: str, skip: tuple[str, ...] = ()):
    """Yield every .md path in the vault, skipping hidden dirs and top-level `skip` folders."""
    for root, dirs, files in os.walk(vault):
        at_top = os.path.normpath(root) == os.path.normpath(vault)
        dirs[:] = [d for d in dirs if not d.startswith(".") and not (at_top and d in skip)]
        for name in files:
            if name.endswith(".md"):
                yield os.path.join(root, name)


def find_related(topic: str, exclude: set[str] | frozenset[str] = frozenset(), limit: int = 3) -> list[Note]:
    """Notes about the same topic as `topic` (title, concept names, tags): for "## Related".

    Only title, alias and tag matches count as evidence, each weighted by how rare
    the term is across the vault, so generic words ("guía", "definición") and
    incidental body mentions can't link unrelated notes. `exclude` is a set of
    note titles to leave out (e.g. the concepts the hub already lists).
    """
    terms = list(dict.fromkeys(_strip_accents(k) for k in keywords(topic)))  # "penélope" == "penelope"
    terms = [t for t in terms if t not in _TITLE_FILLER]
    vault = config.obsidian_vault_path()
    if not terms or not os.path.isdir(vault):
        return []

    patterns = {t: _word_pattern(t) for t in terms}
    excluded = {_strip_accents(t.lower()) for t in exclude}
    pool = []  # (path, title, tags, body, terms matched in title/aliases, terms matched in tags)
    for path in _markdown_files(vault, skip=_RELATED_SKIP_FOLDERS):
        title = note_title(path)
        if _strip_accents(title.lower()) in excluded:
            continue
        try:
            tags, aliases, body = _parse(path)
        except (OSError, UnicodeDecodeError):
            continue
        names = [_strip_accents(title.lower())] + [_strip_accents(a.lower()) for a in aliases]
        tags_n = {_strip_accents(t) for t in tags}
        in_title = {t for t in terms if any(patterns[t].search(n) for n in names)}
        in_real_title = {t for t in in_title if patterns[t].search(names[0])}
        in_tags = {t for t in terms if t in tags_n} - in_title
        pool.append((path, title, tags, body, in_title, in_real_title, in_tags))
    if not pool:
        return []

    # Rarity of each term among the candidates: 1.0 = unique to one note, ~0 = in most.
    # The floor keeps a young vault from calling every term common.
    size = max(len(pool), _RELATED_MIN_POOL)
    document_frequency = {
        t: sum(1 for _, _, _, _, in_title, _, in_tags in pool if t in in_title or t in in_tags)
        for t in terms
    }
    weight = {t: math.log((size + 1) / (df + 1)) / math.log(size + 1) for t, df in document_frequency.items()}

    results: list[Note] = []
    for path, title, tags, body, in_title, in_real_title, in_tags in pool:
        matched = in_title | in_tags
        if not matched or max(weight[t] for t in matched) < RELATED_MIN_TERM_WEIGHT:
            continue
        # One shared word is enough only when it is in the note's own title
        # ("Hamilton"); via an alias or tag ("State" in "State Graph") it is a coincidence.
        if len(matched) < 2 and not matched <= in_real_title:
            continue
        score = sum(3 * weight[t] for t in in_title) + sum(2 * weight[t] for t in in_tags)
        if score < RELATED_MIN_SCORE:
            continue
        body_n = _strip_accents(body.lower())
        score += sum(0.05 * weight[t] for t in terms if patterns[t].search(body_n))  # tie-break only
        results.append(Note(path=path, title=title, body=body.strip(), tags=tags, score=score))

    results.sort(key=lambda n: n.score, reverse=True)
    return results[:limit]


# find_discovery_hub(): is a research request already answered by a saved hub? Compares
# the request's topic words with each hub's original question and its title.
SAME_TOPIC_MIN_OVERLAP = 0.6  # shared words / all words (Jaccard), on topic words only
# Words that frame a request ("explícame", "how does … work") instead of naming its topic.
_REQUEST_FILLER = _TITLE_FILLER | {
    "explain", "explica", "explicame", "investiga", "investigar", "research", "teach",
    "ensename", "quiero", "aprender", "sabes", "dime", "tell", "funcionan", "funcionamiento",
    "work", "mean", "means", "significa",
}


def _frontmatter_value(path: str, key: str) -> str:
    """A quoted scalar from the note's frontmatter (as written by yaml_str), or ""."""
    with open(path, encoding="utf-8") as f:
        content = f.read()
    end = content.find("\n---", 3) if content.startswith("---") else -1
    if end == -1:
        return ""
    match = re.search(rf'^{re.escape(key)}:\s*"(.*)"\s*$', content[3:end], re.MULTILINE)
    return match.group(1).replace('\\"', '"').replace("\\\\", "\\") if match else ""


def topic_terms(text: str) -> set[str]:
    """The words of `text` that name its topic: no stopwords, request verbs or title filler."""
    return {t for t in (_strip_accents(k) for k in keywords(text)) if t not in _REQUEST_FILLER}


def find_discovery_hub(request: str) -> str | None:
    """Path of a saved Discovery hub on the same topic as `request`, or None (newest wins ties).

    "Explícame qué es Docker" matches a hub asked as "¿Qué es Docker?" or titled
    "Fundamentos de Docker", but not one on "Docker networking" (a narrower topic).
    """
    terms = topic_terms(request)
    folder = os.path.join(config.obsidian_vault_path(), "Discovery")
    if not terms or not os.path.isdir(folder):
        return None
    paths = [os.path.join(folder, n) for n in os.listdir(folder) if n.endswith(".md")]
    paths.sort(key=os.path.getmtime, reverse=True)

    best, best_overlap = None, 0.0
    for path in paths:
        try:
            question = _frontmatter_value(path, "question")
        except (OSError, UnicodeDecodeError):
            continue
        for other in (topic_terms(question), topic_terms(note_title(path))):
            if other:
                overlap = len(terms & other) / len(terms | other)
                if overlap > best_overlap:
                    best, best_overlap = path, overlap
    return best if best_overlap >= SAME_TOPIC_MIN_OVERLAP else None
