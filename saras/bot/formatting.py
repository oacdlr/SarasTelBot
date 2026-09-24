"""Turn Gemini's Markdown into the HTML subset Telegram understands.

Telegram only renders a few tags (<b>, <i>, <code>, <pre>, <a>), so headings
become bold lines, checklists become ☐/☑, and [[wiki links]] become links that
open the note in Obsidian.
"""
import html
import re
from urllib.parse import quote

_CODE_BLOCK = re.compile(r"```[^\n]*\n?(.*?)```", re.DOTALL)
_INLINE_CODE = re.compile(r"`([^`\n]+)`")
_WIKI_LINK = re.compile(r"\[\[([^\]|\n]+)(?:\|([^\]\n]+))?\]\]")
_MD_LINK = re.compile(r"\[([^\]\n]+)\]\((https?://[^)\s]+)\)")
_HEADING = re.compile(r"^#{1,6}\s+(.+?)\s*#*$", re.MULTILINE)
_CHECKED = re.compile(r"^(\s*)[-*]\s+\[[xX]\]\s+", re.MULTILINE)
_UNCHECKED = re.compile(r"^(\s*)[-*]\s+\[ \]\s+", re.MULTILINE)
_BULLET = re.compile(r"^(\s*)[-*]\s+", re.MULTILINE)
_BOLD = re.compile(r"\*\*(.+?)\*\*|__(.+?)__")
_ITALIC = re.compile(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])")


def obsidian_url(vault_name: str, note: str) -> str:
    return f"obsidian://open?vault={quote(vault_name, safe='')}&file={quote(note, safe='')}"


def to_telegram_html(text: str, vault_name: str) -> str:
    # Pull code out first so nothing inside it gets formatted.
    saved: list[str] = []

    def keep(fragment: str) -> str:
        saved.append(fragment)
        return f"\x00{len(saved) - 1}\x00"

    text = _CODE_BLOCK.sub(lambda m: keep(f"<pre>{html.escape(m.group(1).strip())}</pre>"), text)
    text = _INLINE_CODE.sub(lambda m: keep(f"<code>{html.escape(m.group(1))}</code>"), text)
    text = _WIKI_LINK.sub(
        lambda m: keep(
            f'<a href="{html.escape(obsidian_url(vault_name, m.group(1).strip()))}">'
            f"{html.escape((m.group(2) or m.group(1)).strip())}</a>"
        ),
        text,
    )
    text = _MD_LINK.sub(
        lambda m: keep(f'<a href="{html.escape(m.group(2))}">{html.escape(m.group(1))}</a>'), text
    )

    text = html.escape(text, quote=False)
    text = _HEADING.sub(r"<b>\1</b>", text)
    text = _CHECKED.sub(r"\1☑ ", text)
    text = _UNCHECKED.sub(r"\1☐ ", text)
    text = _BULLET.sub(r"\1• ", text)
    text = _BOLD.sub(lambda m: f"<b>{m.group(1) or m.group(2)}</b>", text)
    text = _ITALIC.sub(r"<i>\1</i>", text)

    return re.sub(r"\x00(\d+)\x00", lambda m: saved[int(m.group(1))], text)
