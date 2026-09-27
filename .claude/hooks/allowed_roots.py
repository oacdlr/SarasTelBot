"""Folders Claude may touch, shared by guard_paths.py and guard_shell.py.

Besides the project and the vault, this allows Claude Code's own folders for this
project only: its memory, and the temp folder holding its scratchpad and
background-task logs (e.g. the running bot's output).

The vault path comes from .env (OBSIDIAN_VAULT_PATH) rather than being hardcoded,
so moving the vault to a different PC/path only requires editing .env.
"""
import os
import re
import tempfile

PROJECT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# Claude Code names its per-project folders after the project path, e.g. C--Users-...-Saras
PROJECT_SLUG = re.sub(r"[^A-Za-z0-9]", "-", PROJECT)


def _read_vault_path_from_env() -> str:
    # Hooks run under a bare system python (no python-dotenv guaranteed), so
    # .env is parsed by hand instead of importing the dotenv package.
    env_file = os.path.join(PROJECT, ".env")
    try:
        with open(env_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("OBSIDIAN_VAULT_PATH="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    except OSError:
        pass
    return ""


VAULT_PATH = os.environ.get("OBSIDIAN_VAULT_PATH", "").strip() or _read_vault_path_from_env()

ALLOWED_ROOTS = [
    PROJECT,
    os.path.join(os.path.expanduser("~"), ".claude", "projects", PROJECT_SLUG),
    os.path.join(tempfile.gettempdir(), "claude", PROJECT_SLUG),
]
if VAULT_PATH:
    ALLOWED_ROOTS.append(VAULT_PATH)
