"""Detail: expand on a previous answer when the user taps "🔍 Más detalle". Never saves."""
from saras.core.modes.base import ModeResult
from saras.core.persona import DETAIL as SYSTEM
from saras.integrations.gemini_client import ask


async def run(
    message: str, previous: list[ModeResult] | None = None, save: bool = True
) -> ModeResult:  # never writes, so `save` is unused
    earlier = "\n\n".join(r.reply for r in previous or [] if r.reply)
    prompt = f"Topic: {message}\n\nAlready said:\n{earlier}" if earlier else f"Topic: {message}"
    return ModeResult(reply=await ask(prompt, system=SYSTEM))
