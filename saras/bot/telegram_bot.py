"""Telegram interface: the conversational layer of SARAS."""
import asyncio
import itertools
import logging
import os
import re
import time
from collections import Counter
from dataclasses import dataclass
from types import SimpleNamespace

from telegram import (
    BotCommand,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LinkPreviewOptions,
    Message,
    Update,
)
from telegram.constants import ChatAction, ParseMode
from telegram.error import BadRequest, NetworkError
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from saras import config
from saras.bot.formatting import to_telegram_html
from saras.bot.status import format_status
from saras.core.memory import ConversationMemory
from saras.core.modes import chat, detail, discovery, execution, quiz, retrieval
from saras.core.modes.base import ModeResult
from saras.core.router import make_standalone, route
from saras.core.router_log import log_correction
from saras.integrations.gemini_client import ModelUnavailable, QuotaExceeded, health
from saras.integrations.obsidian_vault import (
    count_notes,
    delete_note,
    note_title,
    recent_notes,
    search_notes,
)

log = logging.getLogger(__name__)

MODES = {
    "discovery": discovery.run,
    "retrieval": retrieval.run,
    "execution": execution.run,
    "quiz": quiz.run,
    "detail": detail.run,  # not router-dispatched; only reached via the "🔍 Más detalle" button
}
memory = ConversationMemory()
mode_counts: Counter = Counter()  # requests per mode since the bot started, for /status
started_at = time.time()
nosave_next: set[int] = set()  # chats whose next message should not be written to the Vault
last_routed: dict[int, tuple[str, str]] = {}  # chat_id -> (message, mode) of the last router-chosen answer, for /fix
FIX_MODES = ["discovery", "retrieval", "execution", "quiz", "chat"]
FIX_LABELS = {
    "discovery": "🔎 Investigar", "retrieval": "📚 Recordar", "execution": "📋 Planear",
    "quiz": "🧠 Quiz", "chat": "💬 Charla",
}
TELEGRAM_LIMIT = 4096
CHUNK_LIMIT = 3500  # leaves room for the HTML tags and escapes added by formatting
TYPING_INTERVAL = 4  # Telegram hides "typing…" after about 5 seconds


@dataclass
class PendingAnswer:
    """A Discovery answer whose buttons ("plan"/"detail"/"drop") are still active."""
    result: ModeResult  # the saved Discovery ModeResult, reused as context if acted on
    topic: str  # standalone topic behind it, for the plan objective / detail question
    answer_id: int


_answer_seq = itertools.count(1)
pending_answers: dict[int, PendingAnswer] = {}  # chat_id -> its one active answer keyboard


def _answer_keyboard(answer_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("📋 Planear esto", callback_data=f"ans:plan:{answer_id}"),
        InlineKeyboardButton("🔍 Más detalle", callback_data=f"ans:detail:{answer_id}"),
        InlineKeyboardButton("🗑️ No guardar", callback_data=f"ans:drop:{answer_id}"),
    ]])


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


async def _send(send, text: str, reply_markup: InlineKeyboardMarkup | None = None) -> Message:
    """Send (or edit) with formatting; fall back to plain text if Telegram rejects it."""
    vault_name = os.path.basename(os.path.normpath(config.obsidian_vault_path()))
    try:
        return await send(
            to_telegram_html(text, vault_name),
            parse_mode=ParseMode.HTML,
            link_preview_options=LinkPreviewOptions(is_disabled=True),
            reply_markup=reply_markup,
        )
    except BadRequest as exc:
        log.warning("Telegram rejected formatted reply (%s); sending plain text", exc)
        return await send(text, reply_markup=reply_markup)


async def send_reply(
    update: Update, reply: str, status: Message | None = None, keyboard: InlineKeyboardMarkup | None = None
) -> None:
    """Send the reply in chunks; the first chunk replaces the status message if there is one.

    `keyboard`, if given, is attached under the last chunk only.
    """
    chunks = split_message(reply or "…", limit=CHUNK_LIMIT)
    for i, chunk in enumerate(chunks):
        markup = keyboard if i == len(chunks) - 1 else None
        if i == 0 and status is not None:
            await _send(status.edit_text, chunk, reply_markup=markup)
        else:
            await _send(update.message.reply_text, chunk, reply_markup=markup)


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
    update: Update,
    message: str,
    force_mode: str | None = None,
    save: bool = True,
    previous: list[ModeResult] | None = None,
) -> None:
    """Answer `message`. `force_mode` skips the router (slash commands); `save=False` writes
    nothing. `previous` seeds context for chaining onto an earlier result (e.g. an answer-button
    action), without repeating that earlier result's text in this reply.
    """
    chat_id = update.effective_chat.id
    history = memory.history(chat_id)
    typing = asyncio.create_task(_keep_typing(update.message.chat))
    status: Message | None = None
    keyboard: InlineKeyboardMarkup | None = None
    try:
        steps = [(force_mode, message)] if force_mode else await route(message, history)
        if any(mode == "discovery" for mode, _ in steps):
            status = await update.message.reply_text("🔎 Investigando…")
        results: list[ModeResult] = list(previous or [])
        new_results: list[ModeResult] = []
        topic = message
        for mode, text in steps:
            log.info("Mode: %s%s", mode, "" if save else " (nosave)")
            mode_counts[mode] += 1
            if mode == "chat":  # small talk reads the history itself
                result = await chat.run(text, previous=results, history=history)
            else:
                text = await make_standalone(text, history)
                result = await MODES[mode](text, previous=results, save=save)
            topic = text
            results.append(result)
            new_results.append(result)
        reply = "\n\n———\n\n".join(r.reply for r in new_results)
        memory.add(chat_id, message, reply)
        if force_mode is None and len(steps) == 1:
            last_routed[chat_id] = (message, steps[0][0])
        if new_results and steps[-1][0] == "discovery" and new_results[-1].note_path and save:
            answer_id = next(_answer_seq)
            pending_answers[chat_id] = PendingAnswer(new_results[-1], topic, answer_id)
            keyboard = _answer_keyboard(answer_id)
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
    await send_reply(update, reply, status, keyboard)


async def answer_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """The "📋 Planear esto" / "🔍 Más detalle" / "🗑️ No guardar" buttons under a Discovery answer."""
    query = update.callback_query
    if not is_allowed(update):
        await query.answer()
        return
    try:
        _, action, raw_id = (query.data or "").split(":", 2)
        answer_id = int(raw_id)
    except ValueError:
        await query.answer()
        return

    chat_id = query.message.chat_id
    pending = pending_answers.get(chat_id)
    if pending is None or pending.answer_id != answer_id:
        await query.answer("Ya no disponible. / No longer available.", show_alert=True)
        return

    await query.answer()
    pending_answers.pop(chat_id, None)
    try:
        await query.edit_message_reply_markup(reply_markup=None)  # buttons are one-shot
    except BadRequest:
        pass  # message may already be gone/edited

    if action == "drop":
        delete_note(pending.result.note_path)
        await query.message.reply_text("🗑️ Removed from the Vault. / Eliminado del Vault.")
        return
    if action not in ("plan", "detail"):
        log.warning("Unknown answer-button action: %s", action)
        return

    fake_update = SimpleNamespace(message=query.message, effective_chat=SimpleNamespace(id=chat_id))
    mode = "execution" if action == "plan" else "detail"
    await respond(fake_update, pending.topic, force_mode=mode, previous=[pending.result])


async def fix(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/fix: offer the other modes for the last router-chosen answer, to redo it and log the miss."""
    if not is_allowed(update):
        return
    entry = last_routed.get(update.effective_chat.id)
    if entry is None:
        await update.message.reply_text(
            "Nothing to fix: /fix works right after a message I routed myself. "
            "/ Nada que corregir: úsalo justo después de un mensaje que yo enruté."
        )
        return
    _, used = entry
    buttons = [
        InlineKeyboardButton(FIX_LABELS[m], callback_data=f"fix:{m}") for m in FIX_MODES if m != used
    ]
    await update.message.reply_text(
        f"I used {used}. Which mode should it have been? / Usé {used}. ¿Qué modo era?",
        reply_markup=InlineKeyboardMarkup([buttons[:2], buttons[2:]]),
    )


async def fix_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """A mode button under /fix: log the correction and redo the message in that mode."""
    query = update.callback_query
    if not is_allowed(update):
        await query.answer()
        return
    corrected = (query.data or "").split(":", 1)[-1]
    chat_id = query.message.chat_id
    entry = last_routed.get(chat_id)
    if corrected not in FIX_MODES or entry is None:
        await query.answer("Ya no disponible. / No longer available.", show_alert=True)
        return

    await query.answer()
    last_routed.pop(chat_id, None)
    try:
        await query.edit_message_reply_markup(reply_markup=None)  # one-shot
    except BadRequest:
        pass
    message, routed = entry
    log_correction(message, routed, corrected)
    fake_update = SimpleNamespace(message=query.message, effective_chat=SimpleNamespace(id=chat_id))
    await respond(fake_update, message, force_mode=corrected)


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


async def notes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/notes [n]: the n most recent notes, with links (default 5, max 20)."""
    if not is_allowed(update):
        return
    arg = command_args(update)
    try:
        limit = max(1, min(int(arg), 20)) if arg else 5
    except ValueError:
        await update.message.reply_text("Usage: /notes [n]")
        return
    paths = recent_notes(limit)
    if not paths:
        await update.message.reply_text("No notes saved yet. / Aún no hay notas guardadas.")
        return
    links = "\n".join(f"- [[{note_title(p)}]]" for p in paths)
    await _send(update.message.reply_text, f"📚 Recent notes:\n{links}")


async def search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/search <word>: plain keyword search in the vault, no Gemini call."""
    if not is_allowed(update):
        return
    query = command_args(update)
    if not query:
        await update.message.reply_text("Usage: /search <word>")
        return
    results = search_notes(query, limit=8)
    if not results:
        await update.message.reply_text("No matches. / Sin resultados.")
        return
    links = "\n".join(f"- [[{n.title}]]" for n in results)
    await _send(update.message.reply_text, f"🔍 Matches for “{query}”:\n{links}")


async def clear(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/clear: forgets this chat's remembered conversation (Vault notes are untouched)."""
    if not is_allowed(update):
        return
    if memory.clear(update.effective_chat.id):
        await update.message.reply_text(
            "🧹 Conversation memory cleared. / Memoria de conversación borrada."
        )
    else:
        await update.message.reply_text("Nothing to clear. / No había nada que borrar.")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_allowed(update):
        return
    lines = ["🪷 SARAS — comandos / commands:", ""]
    lines += [f"/{c.command} — {c.description}" for c in COMMAND_MENU]
    lines.append("")
    lines.append(
        "O simplemente escríbeme y yo decido el modo.\n"
        "Or just talk to me — I'll figure out the mode."
    )
    await update.message.reply_text("\n".join(lines))


COMMAND_MENU = [
    BotCommand("research", "Investigar un tema y guardarlo / Research a topic"),
    BotCommand("recall", "Buscar en tus notas / Ask your notes"),
    BotCommand("plan", "Convertir una meta en checklist / Turn a goal into a checklist"),
    BotCommand("quiz", "Examinarte sobre tus notas / Quiz yourself on your notes"),
    BotCommand("notes", "Notas recientes / Recent notes"),
    BotCommand("search", "Buscar palabra clave / Keyword search"),
    BotCommand("last", "Enlace a la última nota / Last saved note"),
    BotCommand("fix", "Corregir el modo elegido / Fix the mode I picked"),
    BotCommand("nosave", "No guardar este mensaje / Don't save this message"),
    BotCommand("clear", "Olvidar la conversación / Forget the conversation"),
    BotCommand("status", "Estado de SARAS / SARAS status"),
    BotCommand("help", "Ver comandos / List commands"),
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
    app.add_handler(CommandHandler(
        ["plan", "planea"], _mode_command("execution", "Usage: /plan <goal>")))
    app.add_handler(CommandHandler("quiz", _mode_command("quiz", "Usage: /quiz <topic>")))
    app.add_handler(CommandHandler(["fix", "mode"], fix))
    app.add_handler(CommandHandler("nosave", nosave))
    app.add_handler(CommandHandler("last", last))
    app.add_handler(CommandHandler("notes", notes))
    app.add_handler(CommandHandler("search", search))
    app.add_handler(CommandHandler("clear", clear))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CallbackQueryHandler(answer_button, pattern=r"^ans:"))
    app.add_handler(CallbackQueryHandler(fix_button, pattern=r"^fix:"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_error_handler(on_error)
    log.info("SARAS is running. Vault: %s", config.obsidian_vault_path())
    app.run_polling()
