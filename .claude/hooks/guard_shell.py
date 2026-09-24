"""PreToolUse hook: block shell commands that name paths outside the project and vault.

A text check, not a sandbox: it reads the command for absolute paths and blocks the
command if any of them falls outside the allowed roots. Relative paths are fine
because the shell runs inside the project.
"""
import json
import os
import re
import sys

from allowed_roots import ALLOWED_ROOTS

# Absolute paths in either Windows (C:\... or C:/...) or Git Bash (/c/...) form.
ABSOLUTE_PREFIX = re.compile(r"""^(?:[A-Za-z]:[\\/]|/[A-Za-z]/|~[\\/])""")
# Only at the start of a word, so URLs (https://host/a/b) aren't mistaken for paths.
PATH_PATTERN = re.compile(r"""(?<![\w.:/\\~-])(?:[A-Za-z]:[\\/]|/[A-Za-z]/|~[\\/])[^\s"'|;&>)]*""")
QUOTED_PATTERN = re.compile(r"""\"([^\"]*)\"|'([^']*)'""")


def candidates(command: str) -> list[str]:
    """Absolute paths named in the command; quoted strings are kept whole."""
    found = []
    for match in QUOTED_PATTERN.finditer(command):
        quoted = match.group(1) if match.group(1) is not None else match.group(2)
        if ABSOLUTE_PREFIX.match(quoted):
            found.append(quoted)
    unquoted = QUOTED_PATTERN.sub(" ", command)
    found.extend(PATH_PATTERN.findall(unquoted))
    return found
# Paths that walk upward out of the project, e.g. ../../elsewhere
ESCAPE_PATTERN = re.compile(r"(?:^|[\s\"'=(])\.\.[\\/]")


def _to_windows(path: str) -> str:
    if path.startswith("~"):
        path = os.path.expanduser(path)
    if len(path) > 2 and path[0] == "/" and path[2] == "/" and path[1].isalpha():
        return f"{path[1]}:{path[2:]}"
    return path


def _norm(path: str) -> str:
    return os.path.normcase(os.path.abspath(_to_windows(path)))


def _inside(path: str, root: str) -> bool:
    try:
        return os.path.commonpath([_norm(path), _norm(root)]) == _norm(root)
    except ValueError:  # different drives
        return False


def _deny(reason: str) -> None:
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }))
    sys.exit(0)


payload = json.load(sys.stdin)
command = payload.get("tool_input", {}).get("command", "")
if not command:
    sys.exit(0)

for raw in candidates(command):
    candidate = raw.rstrip(".,:;")
    if not any(_inside(candidate, root) for root in ALLOWED_ROOTS):
        _deny(
            f"Blocked: this command refers to {candidate}, which is outside the allowed "
            "folders. Only the Saras project, SARAS-Vault and Claude's own folders for this "
            "project are allowed."
        )

if ESCAPE_PATTERN.search(command):
    _deny(
        "Blocked: this command uses '..' to step outside the project. "
        "Use paths inside the Saras folder or SARAS-Vault."
    )
