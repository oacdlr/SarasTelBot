"""Small talk: answer briefly and never write to the Vault."""
from saras.core.memory import Turn, format_history
from saras.core.modes.base import ModeResult
from saras.core.persona import CHAT as SYSTEM
from saras.integrations.gemini_client import ask


async def run(
    message: str, previous: list[ModeResult] | None = None, history: list[Turn] | None = None
) -> ModeResult:
    prompt = message
    if history:
        prompt = f"{format_history(history)}\n\nUser's new message: {message}"
    return ModeResult(reply=await ask(prompt, system=SYSTEM, fast=True))
