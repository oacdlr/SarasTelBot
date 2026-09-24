# SARAS

A personal AI knowledge companion on Telegram. SARAS researches topics (Discovery), answers from your saved notes (Retrieval), and turns goals into plans (Execution). Everything worth keeping goes into an Obsidian Vault as plain Markdown.

See `SARAS-Project-Context.md` for the vision and `SARAS — Implementation Guide.md` for the original v1 design.

## Setup (Windows / PowerShell)

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env   # then fill in the values
```

| Setting | Where to get it |
| --- | --- |
| `TELEGRAM_BOT_TOKEN` | Message @BotFather, run `/newbot` |
| `TELEGRAM_ALLOWED_USER_IDS` | Your numeric Telegram ID, from @userinfobot. Messages from anyone else are ignored. |
| `GEMINI_API_KEY` | Google AI Studio (ai.google.dev) |
| `GEMINI_MODEL` / `GEMINI_FAST_MODEL` | Optional. Main model, and the cheaper model used for routing, titles and chat |
| `OBSIDIAN_VAULT_PATH` | The vault folder (default `C:\Users\oscar\Documents\SARAS-Vault`); open it in Obsidian |

## Run

```powershell
python -m saras.main
```

Then message your bot. `/start` shows what it can do.

## How it works

```
Telegram → router (keywords, Gemini fallback) → mode → reply
                                                  └→ Vault note (only when worth keeping)
```

| Mode | Triggered by (examples) | Writes to Vault |
| --- | --- | --- |
| Discovery | "explain…", "research…", "qué es…", "investiga…" | `Discovery/<title>.md`, with web sources and related-note links |
| Retrieval | "what did I learn…", "remind me…", "qué aprendí…" | nothing; answers only from your notes and cites them |
| Execution | "help me plan…", "due Friday", "organiza…", "entrega…" | `Execution/<title>.md` checklist |
| Chat | greetings, thanks, small talk | nothing |

"Research X and then help me plan Y" runs Discovery, then Execution.

## Code layout

- `saras/config.py`: settings from `.env`, read lazily
- `saras/bot/telegram_bot.py`: Telegram handler, user whitelist, long-message splitting
- `saras/core/router.py`: intent routing and chaining
- `saras/core/modes/`: one module per mode
- `saras/integrations/gemini_client.py`: the only code that calls Gemini, so the provider is swappable
- `saras/integrations/obsidian_vault.py`: writes notes and runs keyword search

## Tests

```powershell
pytest
```

Gemini and Telegram are mocked, so no API keys are needed.

## Known limitations (v1)

- NotebookLM has no public API, so Gemini produces the study material directly.
- Retrieval uses keyword search. An embeddings index would be the natural upgrade.
- Execution creates plans but can't yet update existing checklist items from chat.
- No conversation memory between messages: each message is handled on its own.
