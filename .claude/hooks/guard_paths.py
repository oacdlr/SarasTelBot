"""PreToolUse hook: block Claude file writes outside the SARAS project and vault."""
import json
import os
import sys

from allowed_roots import ALLOWED_ROOTS, PROJECT


def _to_windows(path: str) -> str:
    # Git Bash style /c/Users/... -> c:/Users/...
    if len(path) > 2 and path[0] == "/" and path[2] == "/" and path[1].isalpha():
        return f"{path[1]}:{path[2:]}"
    return path


def _norm(path: str) -> str:
    return os.path.normcase(os.path.realpath(_to_windows(path)))


def _inside(path: str, root: str) -> bool:
    try:
        return os.path.commonpath([_norm(path), _norm(root)]) == _norm(root)
    except ValueError:  # different drives
        return False


payload = json.load(sys.stdin)
tool_input = payload.get("tool_input", {})
path = tool_input.get("file_path") or tool_input.get("notebook_path")
if not path:
    sys.exit(0)
path = _to_windows(path)
if not os.path.isabs(path):
    path = os.path.join(payload.get("cwd") or PROJECT, path)

if not any(_inside(path, root) for root in ALLOWED_ROOTS):
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": (
                f"Blocked: {path} is outside the allowed folders. Only the Saras "
                "project, SARAS-Vault and Claude's own folders for this project may be written."
            ),
        }
    }))
