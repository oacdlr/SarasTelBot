"""Text for the /status command."""
import os
from collections import Counter

from saras.integrations.gemini_client import GeminiHealth

RECENT = 30 * 60  # a problem this recent still counts as "current", in seconds


def ago(then: float | None, now: float) -> str:
    if then is None:
        return "never"
    seconds = max(0, int(now - then))
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        return f"{seconds // 60} min ago"
    if seconds < 86400:
        return f"{seconds // 3600} h ago"
    return f"{seconds // 86400} d ago"


def _duration(seconds: float) -> str:
    seconds = int(seconds)
    if seconds < 60:
        return "<1 min"
    if seconds < 3600:
        return f"{seconds // 60} min"
    if seconds < 86400:
        return f"{seconds // 3600} h {seconds % 3600 // 60} min"
    return f"{seconds // 86400} d {seconds % 86400 // 3600} h"


def _recent(then: float | None, now: float) -> bool:
    return then is not None and now - then < RECENT


def gemini_lines(health: GeminiHealth, now: float) -> list[str]:
    lines = []
    if _recent(health.last_quota_error, now):
        lines.append(f"⚠️ Quota exhausted ({ago(health.last_quota_error, now)})")
    elif _recent(health.last_busy, now):
        lines.append(f"⚠️ Model overloaded ({ago(health.last_busy, now)}); falling back to the fast model")
    else:
        lines.append("✅ No problems since it last worked" if health.last_ok else "No requests yet")

    if _recent(health.last_search_fallback, now):
        lines.append(
            f"⚠️ Web search unavailable ({ago(health.last_search_fallback, now)}): "
            "research answers come without sources"
        )
    elif health.last_search_fallback is not None:
        lines.append(f"Web search fell back {ago(health.last_search_fallback, now)}; fine since")
    if health.last_ok:
        lines.append(f"Last successful request: {ago(health.last_ok, now)}")
    return lines


def format_status(
    *,
    health: GeminiHealth,
    models: tuple[str, str],
    vault_path: str,
    note_counts: dict[str, int],
    mode_counts: Counter,
    started: float,
    now: float,
) -> str:
    vault_ok = os.path.isdir(vault_path)
    notes = " · ".join(f"{folder} {n}" for folder, n in note_counts.items())
    modes = " · ".join(f"{mode} {n}" for mode, n in sorted(mode_counts.items())) or "none yet"
    lines = [
        "🪷 SARAS status",
        "",
        "Gemini",
        f"Models: {models[0]} (fast: {models[1]})",
        *gemini_lines(health, now),
        "",
        "Vault",
        f"{vault_path} {'✅' if vault_ok else '❌ folder not found'}",
        f"Notes: {notes}",
        "",
        f"Since start (up {_duration(now - started)})",
        f"Requests by mode: {modes}",
    ]
    return "\n".join(lines)
