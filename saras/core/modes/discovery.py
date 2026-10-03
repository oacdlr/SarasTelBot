"""Discovery Mode (Learn): research a topic and store it as a hub note + concept notes."""
import json
import re
from datetime import date

from saras.core.modes.base import ModeResult
from saras.core.persona import DISCOVERY_PREFIX, LANGUAGE_RULE
from saras.integrations.gemini_client import ask, research
from saras.integrations.obsidian_vault import (
    bare_list,
    concept_index,
    find_discovery_hub,
    find_related,
    note_title,
    quoted_list,
    reserve_note_path,
    upsert_concept,
    write_raw_note,
    yaml_str,
)

# Section headings and vocabulary the hub/concept templates use, per language.
_STRINGS = {
    "es": {
        "prereq": "Prerrequisitos",
        "key_concepts": "Conceptos clave",
        "foundations": "1. Fundamentos",
        "how_it_works": "2. Cómo funciona",
        "in_practice": "3. En la práctica / estado actual",
        "comparison": "Comparación",
        "uncertainty": "Incertidumbre y preguntas abiertas",
        "next_steps": "Qué aprender después",
        "question_callout": "Pregunta",
        "summary_callout": "Respuesta corta",
        "related": "Relacionado",
        "sources": "Fuentes",
        "why_it_matters": "Por qué importa",
        "example": "Ejemplo",
        "appears_in": "Aparece en",
        "status": "aprendiendo",
        "verb": "es",
        "confidence_labels": {"high": "alta", "medium": "media", "low": "baja"},
    },
    "en": {
        "prereq": "Prerequisites",
        "key_concepts": "Key concepts",
        "foundations": "1. Foundations",
        "how_it_works": "2. How it works",
        "in_practice": "3. In practice / current state",
        "comparison": "Comparison",
        "uncertainty": "Uncertainty and open questions",
        "next_steps": "What to learn next",
        "question_callout": "Question",
        "summary_callout": "Short answer",
        "related": "Related",
        "sources": "Sources",
        "why_it_matters": "Why it matters",
        "example": "Example",
        "appears_in": "Appears in",
        "status": "learning",
        "verb": "is",
        "confidence_labels": {"high": "high", "medium": "medium", "low": "low"},
    },
}

_SPANISH_CHARS = re.compile(r"[áéíóúñ¿¡]", re.IGNORECASE)
_SPANISH_WORDS = re.compile(
    r"\b(que|qué|como|cómo|cual|cuál|donde|dónde|cuando|cuándo|porque|por qué|"
    r"explica|explícame|explicame|investiga|ayúdame|ayudame|organiza|planea|"
    r"aprendí|aprendi|recuérdame|recuerdame|entrega|pendientes)\b",
    re.IGNORECASE,
)

_HEADING_RE = re.compile(r"^##\s", re.MULTILINE)

_EXTRACTION_SYSTEM = (
    "You extract structured data from a researched knowledge note. Reply with ONLY a JSON "
    "object, no code fences and no commentary, matching this shape exactly:\n"
    '{"title": "short, specific note title (max 8 words) answering the request, same '
    'language as the request, no quotes or final punctuation", '
    '"short_answer": "3-5 lines summarizing the core idea/verdict, same language as the '
    'text", "confidence": "high|medium|low", "tags": ["2-4 lowercase hyphenated topic '
    'tags, ALWAYS in English regardless of the text\'s language"], "concepts": '
    '[{"name": "", "aliases": [], "definition": "1-2 sentences", '
    '"why_it_matters": "", "example": ""}]}\n'
    "Include the 2-6 most important concepts from the text."
)


def _is_spanish(message: str) -> bool:
    return bool(_SPANISH_CHARS.search(message)) or bool(_SPANISH_WORDS.search(message))


def _split_source(entry: str) -> tuple[str, str]:
    """Split a "Title - url" source entry (see gemini_client.research) into (title, url)."""
    if " - " in entry:
        title, url = entry.rsplit(" - ", 1)
        return title.strip(), url.strip()
    return entry, entry


def _system_prompt(s: dict) -> str:
    return (
        DISCOVERY_PREFIX
        + "Using the Google Search results, write ONLY the body of a hub "
        "note as Markdown, with exactly these section headings, in this order, and "
        "nothing before the first heading or after the last one:\n"
        f"## {s['prereq']}\n"
        f"## {s['key_concepts']}\n"
        f"## {s['foundations']}\n"
        f"## {s['how_it_works']}\n"
        f"## {s['in_practice']}\n"
        f"## {s['comparison']}\n"
        f"## {s['uncertainty']}\n"
        f"## {s['next_steps']}\n\n"
        f"- {s['prereq']}: bullets '[[Concept]]: why it's needed'; omit this whole section "
        "if the topic has no real prerequisites.\n"
        f"- {s['key_concepts']}: 2-6 bullets '[[Concept]]: one-line definition'.\n"
        f"- {s['foundations']}: what it is and why it exists.\n"
        f"- {s['how_it_works']}: the mechanism, step by step.\n"
        f"- {s['in_practice']}: real-world use, variants, the current state of the art.\n"
        f"- {s['comparison']}: only include this section, as a Markdown table, if the "
        "question compares two or more options; omit it otherwise.\n"
        f"- {s['uncertainty']}: what the sources leave unclear or disagree on, and open "
        "questions worth researching further.\n"
        f"- {s['next_steps']}: 2-4 bullets '[[Topic]]: why it's a good next step', most "
        "natural first. Each is a concrete topic that builds on this one, named like a "
        "short note title, and not one already listed under prerequisites or key concepts.\n\n"
        "Cite claims with [1], [2]... in the order sources are first used. Be accurate, "
        "don't invent sources or facts, and keep the whole note to about 1-2 screens. "
        + LANGUAGE_RULE
    )


def _body_from_first_heading(text: str) -> str:
    match = _HEADING_RE.search(text)
    return text[match.start():].strip() if match else text.strip()


def _fallback_short_answer(text: str) -> str:
    for para in text.split("\n\n"):
        para = para.strip()
        if para and not para.startswith("#"):
            return para[:400]
    return text.strip()[:400]


def _parse_extraction(raw: str, source_text: str) -> dict:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z]*\n?", "", cleaned)
        cleaned = re.sub(r"```$", "", cleaned).strip()
    try:
        data = json.loads(cleaned)
        if not isinstance(data, dict):
            data = {}
    except json.JSONDecodeError:
        data = {}

    title = data.get("title")
    title = title.strip().strip('"\'') if isinstance(title, str) else ""

    short_answer = data.get("short_answer")
    if not isinstance(short_answer, str) or not short_answer.strip():
        short_answer = _fallback_short_answer(source_text)

    confidence = data.get("confidence")
    if confidence not in ("high", "medium", "low"):
        confidence = "medium"

    raw_tags = data.get("tags")
    tags = []
    if isinstance(raw_tags, list):
        tags = [t.strip().lower() for t in raw_tags if isinstance(t, str) and t.strip()][:4]

    concepts = []
    raw_concepts = data.get("concepts")
    if isinstance(raw_concepts, list):
        for c in raw_concepts:
            if not isinstance(c, dict):
                continue
            name = c.get("name")
            if not isinstance(name, str) or not name.strip():
                continue
            raw_aliases = c.get("aliases")
            aliases = (
                [a.strip() for a in raw_aliases if isinstance(a, str) and a.strip()]
                if isinstance(raw_aliases, list)
                else []
            )
            concepts.append(
                {
                    "name": name.strip(),
                    "aliases": aliases,
                    "definition": str(c.get("definition") or "").strip(),
                    "why_it_matters": str(c.get("why_it_matters") or "").strip(),
                    "example": str(c.get("example") or "").strip(),
                }
            )

    return {
        "title": title,
        "short_answer": short_answer.strip(),
        "confidence": confidence,
        "tags": tags,
        "concepts": concepts[:6],
    }


async def _extract(message: str, text: str) -> dict:
    """Title, summary, tags and concepts in one fast call."""
    raw = await ask(f"Request: {message}\n\nText:\n\n{text}", system=_EXTRACTION_SYSTEM, fast=True)
    return _parse_extraction(raw, text)


def _build_concept_content(
    concept: dict, s: dict, hub_title: str, tags: list[str], sources: list[tuple[str, str]]
) -> str:
    lines = [
        "---",
        f"title: {yaml_str(concept['name'])}",
        "type: concept",
        f"date: {date.today().isoformat()}",
        f"status: {s['status']}",
        f"aliases: {quoted_list(concept['aliases'])}",
        f"tags: {bare_list(['concept'] + [t for t in tags if t != 'concept'])}",
        "---",
        "",
        f"**{concept['name']}** {s['verb']} {concept['definition'] or '…'}".rstrip(),
        "",
        f"## {s['why_it_matters']}",
        concept["why_it_matters"] or "—",
        "",
        f"## {s['example']}",
        concept["example"] or "—",
        "",
        f"## {s['appears_in']}",
        f"- [[{hub_title}]]",
    ]
    if sources:
        lines.append("")
        lines.append(f"## {s['sources']}")
        lines.extend(f"- [{name}]({url})" for name, url in sources)
    return "\n".join(lines) + "\n"


def _build_hub_content(
    title: str,
    message: str,
    s: dict,
    confidence: str,
    tags: list[str],
    concept_titles: list[str],
    source_urls: list[str],
    summary: str,
    body: str,
) -> str:
    lines = [
        "---",
        f"title: {yaml_str(title)}",
        "type: discovery",
        f"date: {date.today().isoformat()}",
        f"question: {yaml_str(message)}",
        f"status: {s['status']}",
        f"confidence: {confidence}",
        f"tags: {bare_list(tags)}",
    ]
    if concept_titles:
        lines.append(f"concepts: {quoted_list([f'[[{c}]]' for c in concept_titles])}")
    if source_urls:
        lines.append(f"sources: {quoted_list(source_urls)}")
    lines += ["---", ""]
    lines.append(f"> [!question] {s['question_callout']}")
    lines.append(f"> {message}")
    lines.append("")
    lines.append(f"> [!summary] {s['summary_callout']}")
    lines.extend(f"> {ln}" if ln else ">" for ln in (summary.splitlines() or [""]))
    lines.append("")
    lines.append(body.strip())
    return "\n".join(lines) + "\n"


def _hub_summary(path: str) -> str:
    """The text of the hub's "> [!summary]" callout."""
    with open(path, encoding="utf-8") as f:
        lines = f.read().splitlines()
    start = next((i for i, ln in enumerate(lines) if ln.startswith("> [!summary]")), None)
    if start is None:
        return ""
    summary = []
    for ln in lines[start + 1:]:
        if not ln.startswith(">"):
            break
        summary.append(ln[1:].strip())
    return "\n".join(summary).strip()


def find_existing(message: str) -> ModeResult | None:
    """A saved hub that already answers `message`, so repeat research doesn't duplicate it."""
    path = find_discovery_hub(message)
    if path is None:
        return None
    try:
        summary = _hub_summary(path)
    except (OSError, UnicodeDecodeError):
        return None
    reply = f"📚 Ya investigaste esto / Already researched: [[{note_title(path)}]]"
    if summary:
        reply += f"\n\n{summary}"
    return ModeResult(reply=reply, note_path=path)


async def run(
    message: str, previous: list[ModeResult] | None = None, save: bool = True
) -> ModeResult:
    lang = "es" if _is_spanish(message) else "en"
    s = _STRINGS[lang]

    answer = await research(message, system=_system_prompt(s))
    body = _body_from_first_heading(answer.text)
    extraction = await _extract(message, answer.text)

    grounded = answer.grounded
    if not save:
        reply = extraction["short_answer"]
        if extraction["concepts"]:
            reply += "\n\n" + "\n".join(f"• {c['name']}" for c in extraction["concepts"])
        reply += "\n\n🚫 Not saved to Vault (/nosave)"
        if not grounded:
            reply += "\n⚠️ Sin búsqueda web (cuota de Gemini) — respuesta sin fuentes."
        return ModeResult(reply=reply)

    confidence = extraction["confidence"] if grounded else "low"
    tags = ["discovery"] + [t for t in extraction["tags"] if t != "discovery"]
    if not grounded:
        tags.append("unverified")
    sources = [_split_source(e) for e in answer.sources]

    # Reserve the hub's file first: its final name (unsafe characters stripped, " (2)"
    # on a collision) is what concept backlinks must point to. No await from here to
    # the write, so no other request can take the same path in between.
    hub_path, _ = reserve_note_path("Discovery", extraction["title"] or message)
    title = note_title(hub_path)

    concept_titles = []
    concepts = concept_index()  # one scan of Concepts/ for the whole run
    for concept in extraction["concepts"]:
        path = upsert_concept(
            name=concept["name"],
            aliases=concept["aliases"],
            content=_build_concept_content(concept, s, title, extraction["tags"], sources),
            backlink_heading=s["appears_in"],
            backlink_line=f"- [[{title}]]",
            index=concepts,
        )
        concept_titles.append(note_title(path))
    concept_titles = list(dict.fromkeys(concept_titles))  # two names can match one note

    # Relate by topic (title, concept names, tags), not by the chat message. The hub
    # isn't written yet, and the concepts it already lists are excluded.
    concept_names = [c["name"] for c in extraction["concepts"]]
    topic = " ".join([title, *concept_names, *extraction["tags"]])
    related = find_related(topic, exclude={title, *concept_names, *concept_titles})

    parts = [body]
    if not grounded:
        parts.append(
            "> [!warning] Sin fuentes web / No web sources\n"
            "> Written from the model's own knowledge: web search was unavailable "
            "(Gemini search-grounding quota). Verify before relying on details."
        )
    if related:
        parts.append(f"## {s['related']}\n" + "\n".join(f"- [[{n.title}]]" for n in related))

    if sources:
        parts.append(
            f"## {s['sources']}\n"
            + "\n".join(f"{i}. [{name}]({url})" for i, (name, url) in enumerate(sources, 1))
        )

    content = _build_hub_content(
        title=title,
        message=message,
        s=s,
        confidence=s["confidence_labels"][confidence],
        tags=tags,
        concept_titles=concept_titles,
        source_urls=[url for _, url in sources],
        summary=extraction["short_answer"],
        body="\n\n".join(parts),
    )
    write_raw_note("Discovery", title, content, path=hub_path)

    reply = extraction["short_answer"]
    if concept_titles:
        reply += "\n\n" + "\n".join(f"• [[{c}]]" for c in concept_titles)
    reply += f"\n\n📚 Saved to Vault: [[{title}]]"
    if not grounded:
        reply += "\n⚠️ Sin búsqueda web (cuota de Gemini) — respuesta sin fuentes."
    return ModeResult(reply=reply, note_path=hub_path)
