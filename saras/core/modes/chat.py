"""Small talk: answer briefly and never write to the Vault."""
from saras.core.modes.base import ModeResult
from saras.core.persona import CHAT as SYSTEM
from saras.integrations.gemini_client import ask


async def run(message: str, previous: list[ModeResult] | None = None) -> ModeResult:
    return ModeResult(reply=await ask(message, system=SYSTEM, fast=True))
