# SARAS: notes for Claude Code

## How to work with me
- I run Claude Code in auto mode. Don't end turns asking "should I…?" for work that's clearly part of the plan: `TODO.md` items, fixing errors found in the bot log, running tests, restarting the bot. Do it, then report what changed.
- Only stop to ask when there's a real choice for me to make (two different designs, a change in scope) or before outward-facing or irreversible actions: `git push`, deleting vault notes, anything that spends money.
- Make a git commit only when I ask for one.
- Keep `TODO.md` up to date as items get done.

## Multi-PC setup
This project is worked on from two PCs; the vault (`SARAS-Vault`) lives on
whichever one is current — see `NEW-PC-SETUP.md` for onboarding a machine.
Git only syncs the repo. If you change something that git does **not** track
(`.env`, `.claude/settings.local.json`, or anything else gitignored), flag it
and remind me to make the same change on the other PC by hand — it won't
travel through `git pull`/`push`.
