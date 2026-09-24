"""Folders Claude may touch, shared by guard_paths.py and guard_shell.py.

Besides the project and the vault, this allows Claude Code's own folders for this
project only: its memory, and the temp folder holding its scratchpad and
background-task logs (e.g. the running bot's output).
"""
import os
import re
import tempfile

PROJECT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# Claude Code names its per-project folders after the project path, e.g. C--Users-...-Saras
PROJECT_SLUG = re.sub(r"[^A-Za-z0-9]", "-", PROJECT)

ALLOWED_ROOTS = [
    PROJECT,
    r"C:\Users\oscar\Documents\SARAS-Vault",
    os.path.join(os.path.expanduser("~"), ".claude", "projects", PROJECT_SLUG),
    os.path.join(tempfile.gettempdir(), "claude", PROJECT_SLUG),
]
