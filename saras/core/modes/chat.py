"""Small talk: answer briefly and never write to the Vault."""
from saras.core.modes.base import ModeResult
from saras.integrations.gemini_client import LANGUAGE_RULE, ask

SYSTEM = (
    "You are SARAS, a warm, concise personal knowledge companion. "
    "Reply briefly and naturally. If it helps, mention you can research topics, "
    "recall saved notes, or help plan tasks. " + LANGUAGE_RULE
)


async def run(message: str, previous: list[ModeResult] | None = None) -> ModeResult:
    return ModeResult(reply=await ask(message, system=SYSTEM, fast=True))
