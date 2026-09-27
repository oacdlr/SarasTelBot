# Setting up SARAS on a new PC

The vault is moving to this PC. This is the one-time checklist to get the
project and Claude Code working here.

## 1. Get the project
- [ ] `git clone https://github.com/oacdlr/SarasTelBot.git`
- [ ] Set up GitHub auth on this machine (`gh auth login` or an SSH key) so
      `git pull`/`push` work.

## 2. Python environment
- [ ] Create a venv: `python -m venv .venv`
- [ ] Activate it and install deps: `pip install -r requirements.txt`
      (do **not** copy `.venv/` from the old PC — it bakes in absolute paths).

## 3. Move the vault here
- [ ] Copy the `SARAS-Vault` folder to this PC (USB, cloud sync, whatever's
      convenient) and note the new path, e.g. `C:\Users\<you>\Documents\SARAS-Vault`.

## 4. Recreate `.env`
- [ ] Copy `.env.example` to `.env`.
- [ ] Fill in `TELEGRAM_BOT_TOKEN`, `TELEGRAM_ALLOWED_USER_IDS`,
      `GEMINI_API_KEY`, `GEMINI_MODEL`, `GEMINI_FAST_MODEL` (copy the real
      values over from the old PC via a private channel, not git).
- [ ] Set `OBSIDIAN_VAULT_PATH` to wherever the vault landed in step 3.
      The app and the Claude Code path guards both read this one value, so
      this is the only place the vault path needs to be set.

## 5. Recreate `.claude/settings.local.json`
This file is gitignored (machine-local), so it doesn't come with `git clone`.
Create `.claude/settings.local.json` with:
```json
{
  "permissions": {
    "additionalDirectories": ["<the vault path from step 3>"],
    "blockReadsOutsideWorkingDirectories": true
  },
  "plansDirectory": ".claude/plans",
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Write|Edit|NotebookEdit",
        "hooks": [{ "type": "command", "command": "python \"$CLAUDE_PROJECT_DIR/.claude/hooks/guard_paths.py\"", "timeout": 10, "statusMessage": "Checking write location" }]
      },
      {
        "matcher": "Bash|PowerShell",
        "hooks": [{ "type": "command", "command": "python \"$CLAUDE_PROJECT_DIR/.claude/hooks/guard_shell.py\"", "timeout": 10, "statusMessage": "Checking command paths" }]
      }
    ]
  }
}
```

## 6. Sanity check
- [ ] `pytest -q` passes.
- [ ] Ask Claude Code to read a note from the vault to confirm the path
      guard (`allowed_roots.py`) picked up `OBSIDIAN_VAULT_PATH` correctly.
- [ ] Confirm the bot isn't also running on the old PC at the same time
      (same Telegram token = 409 polling conflict — only one machine should
      run it live).

## Not carried over automatically
- Claude Code's memory for this project (preferences, prior context) lives
  outside the repo at `~/.claude/projects/<project-path-slug>/memory/` on the
  old PC. It only transfers cleanly if you manually copy that folder AND the
  project's absolute path is identical on both machines. Otherwise Claude
  Code just starts fresh here — not a blocker, just expect it to re-learn
  context over time.
