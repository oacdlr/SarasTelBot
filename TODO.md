# SARAS: To-do

Last updated: 2026-09-28

## Done
- [x] Read the project docs and plan v1 (guide + fixes)
- [x] Scaffold the project, venv, dependencies, git repo
- [x] Config, Gemini client, Obsidian Vault integration
- [x] Router (Spanish + English keywords, Gemini fallback, Discovery → Execution chaining)
- [x] Modes: Discovery, Retrieval, Execution, Chat
- [x] Telegram bot (user whitelist, long-message splitting)
- [x] Tests (17 passing, no API keys needed)
- [x] Create the vault at `C:\Users\oscar\Documents\SARAS-Vault`
- [x] Restrict Claude Code to the project + vault (write-guard hook, read block)
- [x] Handle Gemini overload (503): retry, then fall back to the fast model
- [x] Discovery note templates + automatic concept notes

## Now: get it running
- [x] Shell commands restricted by a guard hook (the sandbox isn't available on this machine)
- [x] Create the bot with @BotFather, put the token in `.env`
- [x] Get your Telegram ID from @userinfobot, put it in `TELEGRAM_ALLOWED_USER_IDS`
- [x] Get a Gemini API key from Google AI Studio, put it in `.env`
- [x] Open `SARAS-Vault` in Obsidian
- [x] Start the bot: `.venv\Scripts\python -m saras.main`
- [x] First commit, pushed to github.com/oacdlr/SarasTelBot

## Verify on Telegram
- [x] "Explícame qué es RAG" creates a note in `Discovery/` — confirmed 2026-09-25 (no sources: Gemini search-grounding quota was hit, SARAS degraded gracefully with an `unverified` tag + warning instead of failing)
- [x] "¿Qué aprendí sobre RAG?" finds that note and cites it — confirmed 2026-09-25
- [x] Execution mode creates a checklist in `Execution/` — confirmed 2026-09-25 (tested with a presentation-planning prompt)
- [x] "Investiga X y luego ayúdame a planear Y" runs both modes and links the notes — confirmed 2026-09-25
- [x] "hola" / "gracias" writes nothing — confirmed 2026-09-25 (routed to chat mode, no vault writes)
- [x] A long answer arrives split into several messages — confirmed 2026-09-25
- [x] A message from another Telegram account is ignored — confirmed 2026-09-25, then that account was added to `TELEGRAM_ALLOWED_USER_IDS`

## Chat experience (in priority order)
- [x] Keep "typing…" showing until the answer is ready; for Discovery, send "🔎 Investigando…" right away and replace it with the answer
- [x] Render Gemini's Markdown as Telegram formatting (no raw `**`, `##`, `- [ ]`)
- [x] Make "Saved to Vault" a tappable link that opens the note in Obsidian
- [x] Conversation memory: last 5 exchanges per chat, forgotten after 45 min idle; used in routing, Chat mode, and to rewrite follow-ups like "¿y en Python?" into standalone requests (in RAM only, lost on restart)
- [x] Discovery: send a short summary (5–8 lines) + note link instead of the whole note
- [x] Commands: `/research`, `/recall`, `/plan` to force a mode (see "Commands to-do" below) — all done 2026-09-28
- [x] Buttons under answers: "📋 Planear esto", "🔍 Más detalle", "🗑️ No guardar" — 2026-09-28. "No guardar" only deletes the Discovery hub note; any Concept notes it created/updated are left as-is (unlike `/nosave`, which skips them upfront) — reverting those safely would mean telling apart concept notes/backlinks this run created from ones that already existed, which isn't done
- [x] Let me correct a wrong mode, and log it to feed router tuning — 2026-09-28: `/fix` (alias `/mode`) right after a router-chosen answer offers the other modes; picking one re-runs the message in that mode and appends `{ts, message, routed, corrected}` to `logs/router_corrections.jsonl` (gitignored, per-PC). Slash-command and chained (Discovery → Execution) answers aren't fixable

## Commands to-do
Slash commands skip the router. The menu is registered from code at startup (`COMMAND_MENU` in `telegram_bot.py`), so BotFather needs no setup: add new commands there.
- [x] `/research <topic>` (alias `/investiga`): Discovery mode, skips the router
- [x] `/recall <question>` (alias `/recuerda`): Retrieval from the vault
- [x] `/last`: re-sends the link to the last note saved
- [x] `/status`: Gemini quota/fallback state, vault path and note counts, mode counts since start
- [x] `/nosave`: `/nosave <message>` answers it without writing to the Vault; alone, it arms the next message (send again to cancel)
- [x] `/plan <goal>` (alias `/planea`): Execution checklist — 2026-09-28
- [x] `/quiz <topic>`: quiz on your notes — 2026-09-28 (quiz mode already existed, just wasn't wired to a command)
- [x] `/help`: lists commands and examples — 2026-09-28 (built from `COMMAND_MENU`, stays in sync automatically)
- [x] `/notes [n]`: the n most recent notes, with links — 2026-09-28 (uses `recent_notes()`, default 5, max 20)
- [x] `/search <word>`: plain keyword search in the vault, no Gemini call — 2026-09-28 (uses `search_notes()`)
- [x] `/clear`: clears the remembered conversation — 2026-09-28 (`ConversationMemory.clear(chat_id)` added)

## Next improvements
- [x] Discovery "Related": stricter `find_related()` (topic-based query, rarity-weighted title/tag matches, filler words ignored, max 3, skips Execution/Quizzes/templates); replayed against the real vault, see DEV-GUIDE section 8
- [x] Execution "Related knowledge" now uses `find_related()` instead of the old `search_notes(...) >= 3` rule — 2026-09-28 (existing plan notes keep their old links)
- [ ] Tune router keywords from real usage (read `logs/router_corrections.jsonl`, filled by `/fix`)
- [ ] Execution: check off / update checklist items from chat
- [ ] Retrieval: embeddings index for meaning-based search
- [ ] Discovery: reuse or update an existing note instead of creating a near-duplicate
- [ ] Run SARAS 24/7 (Windows startup task or a small always-on machine)

## Later / blocked
- [ ] NotebookLM integration (blocked: no public API yet)
- [ ] Gemini Deep Research instead of search-grounded answers, if available through the API
- [ ] Voice messages and file uploads (PDFs → Discovery notes)
