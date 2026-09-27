# SARAS: To-do

Last updated: 2026-09-24

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
- [ ] Conversation memory: keep the last few messages per chat and use them in prompts and routing (so follow-ups like "¿y en Python?" work)
- [x] Discovery: send a short summary (5–8 lines) + note link instead of the whole note
- [ ] Commands: `/research`, `/recall`, `/plan` to force a mode
- [ ] Buttons under answers: "📋 Planear esto", "🔍 Más detalle", "🗑️ No guardar"
- [ ] Let me correct a wrong mode, and log it to feed router tuning

## Next improvements
- [ ] Tune router keywords from real usage (log misrouted messages)
- [ ] Execution: check off / update checklist items from chat
- [ ] Retrieval: embeddings index for meaning-based search
- [ ] Discovery: reuse or update an existing note instead of creating a near-duplicate
- [ ] Run SARAS 24/7 (Windows startup task or a small always-on machine)

## Later / blocked
- [ ] NotebookLM integration (blocked: no public API yet)
- [ ] Gemini Deep Research instead of search-grounded answers, if available through the API
- [ ] Voice messages and file uploads (PDFs → Discovery notes)
