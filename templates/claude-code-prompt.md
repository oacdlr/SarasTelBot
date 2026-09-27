Implement the new Discovery note format for SARAS. The templates are already in `templates/`:
- `discovery-hub.es.md` / `discovery-hub.en.md`: the Discovery note
- `concept.es.md` / `concept.en.md`: small reusable concept notes (Zettelkasten)

Read them, plus `saras/core/modes/discovery.py`, `saras/integrations/obsidian_vault.py`, `saras/integrations/gemini_client.py` and `tests/test_modes.py` before changing anything.

## What Discovery should do
1. **Language:** use the Spanish templates when the user's message is Spanish and the English ones otherwise. That covers headings, frontmatter values (`status: aprendiendo`/`learning`, `confidence: alta|media|baja` / `high|medium|low`) and folder-independent text.
2. **Research (grounded):** keep using `research()`. Change the SYSTEM prompt so Gemini writes the body sections of the hub template in order: short answer, prerequisites, key concepts, 1. foundations, 2. how it works, 3. in practice, an optional comparison table (only when the question compares options), and uncertainty/open questions. Claims should cite sources as [1], [2]… in the order of `answer.sources`. Target length is 1–2 screens. The code, not Gemini, writes the frontmatter, the question callout, Related and Sources.
3. **Structured extraction:** make a second, cheap call (`ask(..., fast=True)`) that takes the researched text and returns JSON: `short_answer`, `confidence` (high/medium/low), `tags` (2–4 topic tags, lowercase, hyphenated), and `concepts`, a list of 2–6 items, each with `name`, `aliases`, `definition` (1–2 sentences), `why_it_matters`, `example`. Parse it defensively: on bad JSON, fall back to no concepts and confidence medium. Never crash the reply.
4. **Hub note:** write `Discovery/<title>.md` following the hub template. Frontmatter: title, type: discovery, date, question, status, confidence, tags, concepts (as quoted "[[wikilinks]]"), sources. Put the `> [!question]` and `> [!summary]` callouts at the top. Key concepts are `[[Name]]: definition`. Sources are a numbered list of markdown links. Keep the existing `unverified` tag and warning callout when `answer.grounded` is False, and set confidence to low in that case.
5. **Concept notes (created automatically):** for each concept, look for an existing note in `Concepts/` by filename or `aliases`, matching case- and accent-insensitively.
   - Not found: create `Concepts/<Name>.md` from the concept template (type: concept, status, aliases, tags, definition, why it matters, example, "Aparece en"/"Appears in" linking the hub, sources).
   - Found: do NOT overwrite it. Only append `- [[<hub title>]]` under its "Aparece en"/"Appears in" section if that link isn't there yet.
   - Add helpers for this to `obsidian_vault.py` (e.g. `find_concept`, `upsert_concept`). `write_note` must keep its current never-overwrite behavior.
6. **Telegram reply:** send the short answer, then the key concepts as a short list, then the existing "📚 Saved to Vault" link. Don't send the whole note. This also completes the TODO item "Discovery: send a short summary + note link".
7. **Retrieval:** make sure `search_notes` still works with the new notes. Concept notes should be searchable, and their `aliases` should count like the title. Use `type: concept` notes as supporting context.

## Tests (Gemini mocked, no API keys)
Update `tests/test_modes.py` and add tests for:
- the hub note has the new frontmatter fields and sections (ES and EN)
- concept notes get created
- an existing concept note is not overwritten and gets the backlink appended exactly once
- a concept is matched through an alias and through accent/case differences
- bad JSON from the extraction call still produces a valid hub note
- the ungrounded path still adds `unverified` and confidence low

Run `pytest` until everything passes.

## Then
- Restart the bot: `.venv\Scripts\python -m saras.main`
- Update `TODO.md`: add "Discovery note templates + automatic concept notes" to Done and tick the Discovery summary item. Update the README's Discovery row to mention `Concepts/`.
- Don't commit. Report what changed and anything you couldn't do.
