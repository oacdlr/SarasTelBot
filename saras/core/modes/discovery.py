"""Discovery Mode (Learn): research a topic and store it as a hub note + concept notes."""
import json
import re
from datetime import date

from saras.core.modes.base import ModeResult
from saras.core.persona import DISCOVERY_PREFIX
from saras.integrations.gemini_client import LANGUAGE_RULE, ask, research
from saras.integrations.obsidian_vault import (
    note_title,
    search_notes,
    upsert_concept,
    write_raw_note,
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
    '{"short_answer": "3-5 lines summarizing the core idea/verdict, same language as the '
    'text", "confidence": "high|medium|low", "tags": ["2-4 lowercase hyphenated topic '
    'tags"], "concepts": [{"name": "", "aliases": [], "definition": "1-2 sentences", '
    '"why_it_matters": "", "example": ""}]}\n'
    "Include the 2-6 most important concepts from the text."
)


def _is_spanish(message: str) -> bool:
    return bool(_SPANISH_CHARS.search(message)) or bool(_SPANISH_WORDS.search(message))


def _yaml_str(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _bare_list(items: list[str]) -> str:
    return "[" + ", ".join(items) + "]"


def _quoted_list(items: list[str]) -> str:
    return "[" + ", ".join(_yaml_str(i) for i in items) + "]"


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
        f"## {s['uncertainty']}\n\n"
        f"- {s['prereq']}: bullets '[[Concept]]: why it's needed'; omit this whole section "
        "if the topic has no real prerequisites.\n"
        f"- {s['key_concepts']}: 2-6 bullets '[[Concept]]: one-line definition'.\n"
        f"- {s['foundations']}: what it is and why it exists.\n"
        f"- {s['how_it_works']}: the mechanism, step by step.\n"
        f"- {s['in_practice']}: real-world use, variants, the current state of the art.\n"
        f"- {s['comparison']}: only include this section, as a Markdown table, if the "
        "question compares two or more options; omit it otherwise.\n"
        f"- {s['uncertainty']}: what the sources leave unclear or disagree on, and open "
        "questions worth researching further.\n\n"
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
        "short_answer": short_answer.strip(),
        "confidence": confidence,
        "tags": tags,
        "concepts": concepts[:6],
    }


async def _extract(text: str) -> dict:
    raw = await ask(f"Text:\n\n{text}", system=_EXTRACTION_SYSTEM, fast=True)
    return _parse_extraction(raw, text)


async def _make_title(message: str) -> str:
    return await ask(
        "Write a short, specific title (max 8 words) for a knowledge note answering this "
        "request, in the same language as the request. Reply with the title only, "
        f"no quotes or punctuation at the end.\n\nRequest: {message}",
        fast=True,
    )


def _build_concept_content(
    concept: dict, s: dict, hub_title: str, tags: list[str], sources: list[str]
) -> str:
    lines = [
        "---",
        f"title: {_yaml_str(concept['name'])}",
        "type: concept",
        f"date: {date.today().isoformat()}",
        f"status: {s['status']}",
        f"aliases: {_quoted_list(concept['aliases'])}",
        f"tags: {_bare_list(['concept'] + [t for t in tags if t != 'concept'])}",
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
        lines.extend(f"- [{_split_source(e)[0]}]({_split_source(e)[1]})" for e in sources)
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
        f"title: {_yaml_str(title)}",
        "type: discovery",
        f"date: {date.today().isoformat()}",
        f"question: {_yaml_str(message)}",
        f"status: {s['status']}",
        f"confidence: {confidence}",
        f"tags: {_bare_list(tags)}",
    ]
    if concept_titles:
        lines.append(f"concepts: {_quoted_list([f'[[{c}]]' for c in concept_titles])}")
    if source_urls:
        lines.append(f"sources: {_quoted_list(source_urls)}")
    lines += ["---", ""]
    lines.append(f"> [!question] {s['question_callout']}")
    lines.append(f"> {message}")
    lines.append("")
    lines.append(f"> [!summary] {s['summary_callout']}")
    lines.extend(f"> {ln}" if ln else ">" for ln in (summary.splitlines() or [""]))
    lines.append("")
    lines.append(body.strip())
    return "\n".join(lines) + "\n"


async def run(message: str, previous: list[ModeResult] | None = None) -> ModeResult:
    lang = "es" if _is_spanish(message) else "en"
    s = _STRINGS[lang]

    answer = await research(message, system=_system_prompt(s))
    title = (await _make_title(message)).strip().strip('"\'') or message
    body = _body_from_first_heading(answer.text)
    extraction = await _extract(answer.text)

    grounded = answer.grounded
    confidence = extraction["confidence"] if grounded else "low"
    tags = ["discovery"] + [t for t in extraction["tags"] if t != "discovery"]
    if not grounded:
        tags.append("unverified")

    # Search before writing anything, so this run's own new notes can't show up as "related".
    related = [n for n in search_notes(f"{title} {message}", limit=5) if n.score >= 3]

    concept_titles = []
    for concept in extraction["concepts"]:
        path = upsert_concept(
            name=concept["name"],
            aliases=concept["aliases"],
            content=_build_concept_content(concept, s, title, extraction["tags"], answer.sources),
            backlink_heading=s["appears_in"],
            backlink_line=f"- [[{title}]]",
        )
        concept_titles.append(note_title(path))

    parts = [body]
    if not grounded:
        parts.append(
            "> [!warning] Sin fuentes web / No web sources\n"
            "> Written from the model's own knowledge: web search was unavailable "
            "(Gemini search-grounding quota). Verify before relying on details."
        )
    if related:
        parts.append(f"## {s['related']}\n" + "\n".join(f"- [[{n.title}]]" for n in related))

    source_urls = [_split_source(e)[1] for e in answer.sources]
    if answer.sources:
        parts.append(
            f"## {s['sources']}\n"
            + "\n".join(
                f"{i}. [{_split_source(e)[0]}]({_split_source(e)[1]})"
                for i, e in enumerate(answer.sources, 1)
            )
        )

    content = _build_hub_content(
        title=title,
        message=message,
        s=s,
        confidence=s["confidence_labels"][confidence],
        tags=tags,
        concept_titles=concept_titles,
        source_urls=source_urls,
        summary=extraction["short_answer"],
        body="\n\n".join(parts),
    )
    path = write_raw_note("Discovery", title, content)

    reply = extraction["short_answer"]
    if extraction["concepts"]:
        reply += "\n\n" + "\n".join(f"• [[{c['name']}]]" for c in extraction["concepts"])
    reply += f"\n\n📚 Saved to Vault: [[{note_title(path)}]]"
    if not grounded:
        reply += "\n⚠️ Sin búsqueda web (cuota de Gemini) — respuesta sin fuentes."
    return ModeResult(reply=reply, note_path=path)
