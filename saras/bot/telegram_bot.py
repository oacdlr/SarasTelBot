"""Telegram interface: the conversational layer of SARAS."""
import asyncio
import logging
import os

from telegram import LinkPreviewOptions, Message, Update
from telegram.constants import ChatAction, ParseMode
from telegram.error import BadRequest, NetworkError
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters

from saras import config
from saras.bot.formatting import to_telegram_html
from saras.core.modes import chat, discovery, execution, quiz, retrieval
from saras.core.modes.base import ModeResult
from saras.core.router import route
from saras.integrations.gemini_client import ModelUnavailable, QuotaExceeded

log = logging.getLogger(__name__)

MODES = {
    "discovery": discovery.run,
    "retrieval": retrieval.run,
    "execution": execution.run,
    "quiz": quiz.run,
    "chat": chat.run,
}
TELEGRAM_LIMIT = 4096
CHUNK_LIMIT = 3500  # leaves room for the HTML tags and escapes added by formatting
TYPING_INTERVAL = 4  # Telegram hides "typing…" after about 5 seconds


def split_message(text: str, limit: int = TELEGRAM_LIMIT) -> list[str]:
    """Split text into Telegram-sized chunks, preferring paragraph/line boundaries."""
    chunks = []
    while len(text) > limit:
        cut = text.rfind("\n\n", 0, limit)
        if cut <= 0:
            cut = text.rfind("\n", 0, limit)
        if cut <= 0:
            cut = text.rfind(" ", 0, limit)
        if cut <= 0:
            cut = limit
        chunks.append(text[:cut].rstrip())
        text = text[cut:].lstrip()
    if text.strip():
        chunks.append(text)
    return chunks


def is_allowed(update: Update) -> bool:
    user = update.effective_user
    return user is not None and user.id in config.telegram_allowed_user_ids()


async def _keep_typing(chat) -> None:
    while True:
        try:
            await chat.send_action(ChatAction.TYPING)
        except NetworkError:
            pass
        await asyncio.sleep(TYPING_INTERVAL)


async def _send(send, text: str) -> Message:
    """Send (or edit) with formatting; fall back to plain text if Telegram rejects it."""
    vault_name = os.path.basename(os.path.normpath(config.obsidian_vault_path()))
    try:
        return await send(
            to_telegram_html(text, vault_name),
            parse_mode=ParseMode.HTML,
            link_preview_options=LinkPreviewOptions(is_disabled=True),
        )
    except BadRequest as exc:
        log.warning("Telegram rejected formatted reply (%s); sending plain text", exc)
        return await send(text)


async def send_reply(update: Update, reply: str, status: Message | None = None) -> None:
    """Send the reply in chunks; the first chunk replaces the status message if there is one."""
    for i, chunk in enumerate(split_message(reply or "…", limit=CHUNK_LIMIT)):
        if i == 0 and status is not None:
            await _send(status.edit_text, chunk)
        else:
            await _send(update.message.reply_text, chunk)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_allowed(update):
        log.warning("Ignoring message from unauthorized user %s", update.effective_user)
        return
    message = update.message.text
    typing = asyncio.create_task(_keep_typing(update.message.chat))
    status: Message | None = None
    try:
        steps = await route(message)
        if any(mode == "discovery" for mode, _ in steps):
            status = await update.message.reply_text("🔎 Investigando…")
        results: list[ModeResult] = []
        for mode, text in steps:
            log.info("Mode: %s", mode)
            results.append(await MODES.get(mode, chat.run)(text, previous=results))
        reply = "\n\n———\n\n".join(r.reply for r in results)
    except QuotaExceeded:
        log.warning("Gemini quota exhausted")
        reply = (
            "⚠️ Se agotó la cuota de Gemini por ahora. Inténtalo más tarde o revisa "
            "tu plan en https://ai.dev/rate-limit\n"
            "(Gemini quota exhausted — try again later.)"
        )
    except ModelUnavailable:
        log.warning("Gemini overloaded")
        reply = (
            "⚠️ Gemini está saturado en este momento. Inténtalo de nuevo en un minuto.\n"
            "(Gemini is overloaded right now — try again in a minute.)"
        )
    except NetworkError:
        log.warning("Network error while handling message")
        reply = "⚠️ Sin conexión al responder. Vuelve a intentarlo. / Network problem, please retry."
    except Exception:
        log.exception("Failed to handle message")
        reply = "⚠️ Something went wrong on my side. Check the SARAS logs. / Algo falló; revisa los logs."
    finally:
        typing.cancel()
    await send_reply(update, reply, status)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_allowed(update):
        return
    await update.message.reply_text(
        "Hola, soy SARAS 🪷 Tu compañera de estudio. / Your study companion.\n"
        "• Research or explain something → I dig in and save it\n"
        "• What you learned before → Thoth pulls it from the Vault\n"
        "• Plan or organize a task → Athena builds the checklist\n"
        "• \"Quiz me on …\" → I test what you've learned"
    )


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log one line for connection trouble instead of a full traceback per retry."""
    error = context.error
    if isinstance(error, NetworkError):
        log.warning("Telegram connection problem: %s", error)
    else:
        log.error("Unhandled error", exc_info=error)


def main() -> None:
    logging.basicConfig(format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    config.telegram_allowed_user_ids()  # fail fast if the whitelist is missing
    app = ApplicationBuilder().token(config.telegram_bot_token()).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_error_handler(on_error)
    log.info("SARAS is running. Vault: %s", config.obsidian_vault_path())
    app.run_polling()
