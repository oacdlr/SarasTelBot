# Review to-do (from `review 30-9.md`)

Last updated: 2026-10-02

Work from the 2026-09-30 code review, split into sessions you can do separately.
Numbers (1.1, 2.3…) point to the matching section in `review 30-9.md`.
Each session ends the same way: `.venv\Scripts\python -m pytest -q` passes, new tests are added
for what changed, the bot is restarted and checked on Telegram, and the items here and in
`TODO.md` are ticked.

Sessions 1–4 don't depend on each other. Session 5 is easier after session 4, because both
touch `obsidian_vault.py`.

## Session 1: Discovery note correctness (`discovery.py`, `obsidian_vault.py`)
- [x] 1.1 Reserve the hub path before writing concepts, so backlinks use the real title
      (`reserve_note_path()`, `write_raw_note(..., path=)`). Test with a `?`/`:` title and a duplicate title
- [x] 1.1 Fix the existing broken backlinks to `Qué es RAG y cómo funciona` in the vault
      (vault edit: confirm before doing it)
- [x] 1.2 Telegram reply: link concepts by their real note titles (`concept_titles`)
- [x] 3.1 Put `title` in the extraction JSON and remove `_make_title` (one fewer Gemini call)
- [x] 3.2 With `/nosave`, return before `find_related` and building the sections
- [x] 2.6 Unpack `_split_source` once and keep a single `_yaml_str`/`_bare_list` in `obsidian_vault.py`
- [x] Check on Telegram: research the same topic twice; the second hub's concepts link to `… (2)`

## Session 2: Telegram bot handlers (`telegram_bot.py`, `memory.py`)
- [x] 1.3 Ignore edited messages (`filters.UpdateType.MESSAGE` on every handler)
- [x] 1.4 Store the `save` flag in `last_routed`, so `/fix` respects `/nosave`
- [x] 1.4 Clear `last_routed` after slash-command and chained answers
- [x] 1.4 `ConversationMemory.drop_last()`: remove the misrouted turn before the `/fix` redo
- [x] 3.4 Add `respond(..., standalone=True)` for answer buttons and `/fix`, which skips `make_standalone`
- [x] Check on Telegram: edit a sent message and confirm the log has no traceback; send `/nosave` + a message,
      then `/fix`, and confirm nothing is written

## Session 3: Router and module boundaries (`router.py`, `gemini_client.py`, `persona.py`)
- [x] 1.5 Tighten `due`/`entrega`/`pendientes` to phrases and add regression tests
- [x] 2.5 Move `classify_intent` and `INTENT_LABELS` into `router.py`
- [x] 2.5 Move `LANGUAGE_RULE` into `persona.py` (update imports in discovery/persona)
- [x] 2.5 Derive `FIX_MODES` in `telegram_bot.py` from the router's labels
- [x] 4 Remove the extra `" "` before `LANGUAGE_RULE` in `persona.CHAT`
- [x] Check on Telegram: "Explícame qué es la entrega continua" routes to Discovery

## Session 4: Vault search (`obsidian_vault.py`, `retrieval.py`, `quiz.py`)
- [x] 2.1 `search_notes(skip=("templates",))`; Quiz passes `skip=("templates", "Quizzes")` and drops its path filter
- [x] 2.2 Add `Note.relevance` (score without the recency boost) and filter `MIN_SCORE` on it
- [x] 3.5 Compile the term patterns once in `search_notes`
- [x] 3.5 Look up name and aliases from a single concept index in `upsert_concept`, instead of one `find_concept` scan each
- [x] 2.4 `write_note(note_type=...)` → `type: execution` / `type: quiz` in frontmatter

## Session 5: Execution/Detail context and cleanup
- [ ] 2.3 Add a `read_note_body(path)` helper; Execution and Detail use the hub body, falling back to `r.reply`
- [ ] 3.3 Run the plan and the title concurrently with `asyncio.gather`
- [x] 4 Delete `saras/persona_draft.py` (tracked, unused) and its mention in `DEV-GUIDE.txt:204`

## Later (decide first)
- [ ] When `/fix` redoes a misrouted Discovery answer, delete the saved note? (behavior change)
- [ ] Pin versions in `requirements.txt` (`pip freeze`), so both PCs run the same versions
- [ ] Split long replies after HTML conversion, so link-heavy replies keep their formatting
- [ ] Delete the local `saras/.backup_prepersona/` folder (gitignored) if it's no longer needed
