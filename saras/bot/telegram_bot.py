"""Telegram interface: the conversational layer of SARAS."""
import asyncio
import logging
import os
import re
import time
from collections import Counter

from telegram import BotCommand, LinkPreviewOptions, Message, Update
from telegram.constants import ChatAction, ParseMode
from telegram.error import BadRequest, NetworkError
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters

from saras import config
from saras.bot.formatting import to_telegram_html
from saras.bot.status import format_status
from saras.core.memory import ConversationMemory
from saras.core.modes import chat, discovery, execution, quiz, retrieval
from saras.core.modes.base import ModeResult
from saras.core.router import make_standalone, route
from saras.integrations.gemini_client import ModelUnavailable, QuotaExceeded, health
from saras.integrations.obsidian_vault import count_notes, note_title, recent_notes

log = logging.getLogger(__name__)

MODES = {
    "discovery": discovery.run,
    "retrieval": retrieval.run,
    "execution": execution.run,
    "quiz": quiz.run,
}
memory = ConversationMemory()
mode_counts: Counter = Counter()  # requests per mode since the bot started, for /status
started_at = time.time()
nosave_next: set[int] = set()  # chats whose next message should not be written to the Vault
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


def _take_save_flag(chat_id: int) -> bool:
    """Whether this message may write to the Vault; consumes a pending /nosave."""
    if chat_id in nosave_next:
        nosave_next.discard(chat_id)
        return False
    return True


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_allowed(update):
        log.warning("Ignoring message from unauthorized user %s", update.effective_user)
        return
    await respond(update, update.message.text, save=_take_save_flag(update.effective_chat.id))


async def respond(
    update: Update, message: str, force_mode: str | None = None, save: bool = True
) -> None:
    """Answer `message`. `force_mode` skips the router (slash commands); `save=False` writes nothing."""
    chat_id = update.effective_chat.id
    history = memory.history(chat_id)
    typing = asyncio.create_task(_keep_typing(update.message.chat))
    status: Message | None = None
    try:
        steps = [(force_mode, message)] if force_mode else await route(message, history)
        if any(mode == "discovery" for mode, _ in steps):
            status = await update.message.reply_text("🔎 Investigando…")
        results: list[ModeResult] = []
        for mode, text in steps:
            log.info("Mode: %s%s", mode, "" if save else " (nosave)")
            mode_counts[mode] += 1
            if mode == "chat":  # small talk reads the history itself
                result = await chat.run(text, previous=results, history=history)
            else:
                text = await make_standalone(text, history)
                result = await MODES[mode](text, previous=results, save=save)
            results.append(result)
        reply = "\n\n———\n\n".join(r.reply for r in results)
        memory.add(chat_id, message, reply)
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


def command_args(update: Update) -> str:
    """Everything after the command word, keeping line breaks ("/research@bot topic")."""
    match = re.match(r"/\S+\s*(.*)", update.message.text or "", re.DOTALL)
    return match.group(1).strip() if match else ""


def _mode_command(mode: str, usage: str):
    async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not is_allowed(update):
            return
        text = command_args(update)
        if not text:
            await update.message.reply_text(usage)
            return
        await respond(update, text, force_mode=mode, save=_take_save_flag(update.effective_chat.id))

    return handler


async def nosave(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/nosave <message> answers it without writing to the Vault; alone, it arms the next message."""
    if not is_allowed(update):
        return
    text = command_args(update)
    if text:
        await respond(update, text, save=False)
        return
    chat_id = update.effective_chat.id
    if chat_id in nosave_next:
        nosave_next.discard(chat_id)
        await update.message.reply_text("Vault writes back on for your next message. / Guardado reactivado.")
    else:
        nosave_next.add(chat_id)
        await update.message.reply_text(
            "🚫 Your next message won't be written to the Vault. Send /nosave again to cancel.\n"
            "Tu próximo mensaje no se guardará en el Vault."
        )


async def last(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_allowed(update):
        return
    paths = recent_notes(1)
    if not paths:
        await update.message.reply_text("No notes saved yet. / Aún no hay notas guardadas.")
        return
    await _send(update.message.reply_text, f"📚 Last note: [[{note_title(paths[0])}]]")


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_allowed(update):
        return
    await update.message.reply_text(
        format_status(
            health=health,
            models=(config.gemini_model(), config.gemini_fast_model()),
            vault_path=config.obsidian_vault_path(),
            note_counts=count_notes(),
            mode_counts=mode_counts,
            started=started_at,
            now=time.time(),
        )
    )


COMMAND_MENU = [
    BotCommand("research", "Investigar un tema y guardarlo / Research a topic"),
    BotCommand("recall", "Buscar en tus notas / Ask your notes"),
    BotCommand("last", "Enlace a la última nota / Last saved note"),
    BotCommand("nosave", "No guardar este mensaje / Don't save this message"),
    BotCommand("status", "Estado de SARAS / SARAS status"),
]


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log one line for connection trouble instead of a full traceback per retry."""
    error = context.error
    if isinstance(error, NetworkError):
        log.warning("Telegram connection problem: %s", error)
    else:
        log.error("Unhandled error", exc_info=error)


async def register_commands(app) -> None:
    await app.bot.set_my_commands(COMMAND_MENU)


def main() -> None:
    logging.basicConfig(format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    config.telegram_allowed_user_ids()  # fail fast if the whitelist is missing
    app = ApplicationBuilder().token(config.telegram_bot_token()).post_init(register_commands).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler(
        ["research", "investiga"], _mode_command("discovery", "Usage: /research <topic>")))
    app.add_handler(CommandHandler(
        ["recall", "recuerda"], _mode_command("retrieval", "Usage: /recall <question>")))
    app.add_handler(CommandHandler("nosave", nosave))
    app.add_handler(CommandHandler("last", last))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_error_handler(on_error)
    log.info("SARAS is running. Vault: %s", config.obsidian_vault_path())
    app.run_polling()
