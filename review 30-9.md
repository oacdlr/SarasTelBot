# SARAS code review — 2026-09-30

> Review only: nothing below has been implemented yet. Work is tracked in `review to-do.md`.

## Context
Asked for a review of the whole codebase (~2.5k lines of Python, 96 tests passing) looking for
inconsistencies and things to optimize. I read every module under `saras/`, the hooks, TODO and
templates, and checked the real vault. Below are the findings I propose to fix, ordered by impact.
Two of them are confirmed in live data (see ★).

---

## 1. Bugs

**1.1 ★ Concept backlinks / hub title can point to the wrong note** — `core/modes/discovery.py:298-316, 365`
Concepts get `- [[{title}]]` using the raw Gemini title, but the hub is written later through
`_reserve_path`, which strips `: ? # / …` and adds ` (2)` on collisions. Confirmed in the vault:
`Discovery/Qué es RAG y cómo funciona (2).md` exists, and its concept notes link to
`[[Qué es RAG y cómo funciona]]`, which doesn't exist.
Fix: reserve the hub path *first*, then use the final title everywhere (concept content,
backlinks, `find_related` exclude). Make `_reserve_path` public as `reserve_note_path()` in
`integrations/obsidian_vault.py` and let `write_raw_note` take an already-reserved path
(e.g. `write_raw_note(folder, title, content, path=None)`).

**1.2 Concept links in the Telegram reply use the raw name** — `discovery.py:369`
`[[c['name']]]` breaks when `upsert_concept` matched an existing note by alias or `safe_title`
changed the name. Use `concept_titles` (the real note titles, already computed).

**1.3 ★ Edited messages crash handlers** — `bot/telegram_bot.py:491-509`
PTB's `CommandHandler` (and `MessageHandler` with `filters.TEXT`) also fire on *edited* messages
(confirmed in the installed PTB source), where `update.message` is `None` →
`AttributeError` in every handler. Fix: add `filters.UpdateType.MESSAGE` to the text handler
(`filters.TEXT & ~filters.COMMAND & filters.UpdateType.MESSAGE`) and pass
`filters=filters.UpdateType.MESSAGE` to each `CommandHandler` (a small helper to avoid repeating it).

**1.4 `/fix` ignores `/nosave` and goes stale** — `telegram_bot.py:206-207, 318`
- The redo always runs with `save=True`, so fixing a `/nosave` message writes to the Vault.
  Store the `save` flag in `last_routed` and pass it through.
- `last_routed` is never cleared when a later slash command or chained request runs, so `/fix`
  can redo an older, unrelated message. Pop it whenever `respond` doesn't set it.
- The redo appends a second turn for the same message to conversation memory; drop the
  misrouted turn first (add `ConversationMemory.drop_last(chat_id)` in `core/memory.py`).

**1.5 Router keywords that misroute common study questions** — `core/router.py:24-29`
Execution is checked before Discovery, and some execution keywords are generic words:
"qué son las **pendientes** de una recta" → execution, "explícame la **entrega** continua" →
execution, "why did X fall, **due** to …" → execution. Tighten to phrases:
`due` → `due date`, `is due`, `due by`; `entrega` → `mi entrega`, `fecha de entrega`, `entregar`;
`pendientes` → `mis pendientes`, `tengo pendientes`. Add regression tests in `tests/test_router.py`.

## 2. Inconsistencies

**2.1 `search_notes` includes the vault's `templates/` folder**, while `find_related` skips it.
Retrieval/Quiz/`/search` can cite template files. Give `search_notes` a
`skip: tuple[str, ...] = ("templates",)` parameter (reusing `_markdown_files(vault, skip)`), and
have Quiz pass `skip=("templates", "Quizzes")` instead of its path-splitting filter
(`core/modes/quiz.py:29-33`), which also lets past quizzes eat into its 4-note limit.

**2.2 Retrieval/Quiz `MIN_SCORE` is inflated by the recency boost** — `obsidian_vault.py:304-305`
A single body mention in a note written today scores 1.1 + ~1.0 ≥ 2.0, so the "too weak"
threshold barely filters anything in a young vault. Add `relevance` to `Note` (the score before the
recency boost), keep `score` for ranking, and filter on `relevance` in `retrieval.py` / `quiz.py`.

**2.3 Execution and Detail only see the short summary of the Discovery note** —
`core/modes/execution.py:15-18`, `core/modes/detail.py:10`
"Research already done" (capped at 8000 chars) is actually `r.reply`: ~5 lines plus link lines.
Read the hub body from `r.note_path` (new `read_note_body(path)` helper built on `_parse`), falling
back to `r.reply` if the file is gone (e.g. after "🗑️ No guardar").

**2.4 Execution/Quiz notes have no `type:` in frontmatter** while Discovery/Concept notes do.
`write_note` gains a `note_type` argument → `type: execution` / `type: quiz` (useful for Dataview).

**2.5 Module boundaries don't match their docstrings**
- `classify_intent` (routing prompt + label parsing) lives in `gemini_client.py`, which says it's
  "the only module that talks to the Gemini API … swappable". Move it to `core/router.py`
  (tests already patch `saras.core.router.classify_intent`, so they keep working).
- `LANGUAGE_RULE` is prompt text; move it from `gemini_client.py` to `core/persona.py`.
- Mode lists are duplicated in `INTENT_LABELS`, `FIX_MODES` and `KEYWORDS`: derive `FIX_MODES`
  from the router's label tuple.

**2.6 Duplicated helpers**: `_yaml_str` exists in both `discovery.py` and `obsidian_vault.py`;
the inline tag list in `write_note` duplicates `_bare_list`. Keep one copy in `obsidian_vault.py`.
`_split_source(e)` is called twice per source (`discovery.py:251, 340-341`); unpack once.

## 3. Optimizations (mostly fewer Gemini calls, which matters on the free quota)

**3.1 Discovery: fold the title into the extraction call** — `discovery.py:215-221, 298-300`
Title and extraction are two separate fast-model calls. Add `"title"` to the `_EXTRACTION_SYSTEM`
JSON (pass the original request in the prompt), fall back to the message. −1 call per research.

**3.2 Discovery `/nosave`: return before the unused work** — `discovery.py:319-352`
With `save=False`, `find_related` (full vault walk) and the sources/related sections are built and
then thrown away. Move the `if not save` branch right after extraction.

**3.3 Execution: run plan and title in parallel** — `execution.py:20-27`
The title only depends on the objective; `asyncio.gather` it with the plan when `save` is true.

**3.4 Skip `make_standalone` when the text is already standalone** — `telegram_bot.py:199`
Answer buttons pass `pending.topic` (already rewritten) and `/fix` redoes a message that was
already rewritten on the first run; both currently pay an extra Gemini call and risk drift.
Store the rewritten text (in `PendingAnswer.topic` — already — and in `last_routed`) and add a
`standalone: bool` parameter to `respond` that skips the rewrite.

**3.5 Small vault-scan cleanups** — `obsidian_vault.py`
- `search_notes` recompiles `_word_pattern(term)` for every note; build the patterns once
  (like `find_related` already does).
- `upsert_concept` calls `find_concept` once per name/alias, and each call re-reads every concept
  note. Build one `{normalized name/alias: path}` index per call of `upsert_concept`
  (or pass it in from Discovery for all concepts of a run).

## 4. Cleanup
- Delete `saras/persona_draft.py`: tracked in git, imported nowhere, superseded by `core/persona.py`
  (update the one mention in `DEV-GUIDE.txt:204`).
- `persona.CHAT` adds an extra `" "` before `LANGUAGE_RULE` (other prompts don't).
- `saras/.backup_prepersona/` is a local (gitignored) leftover; I'll leave it and just mention it.

## Not doing (noted for later)
- Deleting the misrouted note when `/fix` redoes a Discovery answer (behavior change; ask first).
- mtime-keyed parse cache for the vault: not worth it at ~150 notes vs. seconds of Gemini latency.
- Splitting after HTML conversion (link-heavy replies can exceed 4096 and fall back to plain text).
- Pinning `requirements.txt` versions for the two-PC setup (worth doing with `pip freeze`; separate change).

## Files touched
`saras/bot/telegram_bot.py`, `saras/core/router.py`, `saras/core/memory.py`, `saras/core/persona.py`,
`saras/core/modes/{discovery,execution,detail,retrieval,quiz}.py`,
`saras/integrations/{gemini_client,obsidian_vault}.py`, delete `saras/persona_draft.py`,tests.

## Verification
1. `.venv\Scripts\python -m pytest -q` — all existing tests pass, plus new tests for:
   hub title with `?`/`:` and duplicate title → concept backlink matches the real filename (1.1);
   reply concept links use real titles (1.2); `/fix` after `/nosave` doesn't save and `/fix` after a
   slash command says "nothing to fix" (1.4); router regressions (1.5); `search_notes` skips
   `templates/` (2.1); recency no longer lifts a single body hit past `MIN_SCORE` (2.2);
   Execution prompt contains the hub body (2.3); Discovery makes 2 Gemini calls, not 3 (3.1);
   buttons don't call `make_standalone` (3.4).
2. Restart the bot and check on Telegram: "Explícame qué es la entrega continua" → Discovery;
   edit a sent message → no traceback in the log; research a topic twice → the second hub's concept
   notes link to `… (2)`; `/nosave` + message, then `/fix` → nothing written.
3. Update `TODO.md` with what was done.
