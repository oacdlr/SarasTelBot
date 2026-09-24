from saras.bot.formatting import obsidian_url, to_telegram_html


def test_headings_bold_and_italic():
    html = to_telegram_html("## Qué es RAG\n**Retrieval** augmented *generation*", "SARAS-Vault")
    assert html == "<b>Qué es RAG</b>\n<b>Retrieval</b> augmented <i>generation</i>"


def test_bullets_and_checklists():
    html = to_telegram_html("- one\n* two\n- [ ] todo\n- [x] done", "SARAS-Vault")
    assert html == "• one\n• two\n☐ todo\n☑ done"


def test_escapes_html_and_keeps_code_untouched():
    html = to_telegram_html("a < b & c\n`x **y**`\n```\nif a<b: pass\n```", "SARAS-Vault")
    assert html == "a &lt; b &amp; c\n<code>x **y**</code>\n<pre>if a&lt;b: pass</pre>"


def test_wiki_link_opens_note_in_obsidian():
    html = to_telegram_html("📚 Saved to Vault: [[Qué es RAG]]", "SARAS-Vault")
    url = obsidian_url("SARAS-Vault", "Qué es RAG")
    assert url == "obsidian://open?vault=SARAS-Vault&file=Qu%C3%A9%20es%20RAG"
    assert html == f'📚 Saved to Vault: <a href="{url.replace("&", "&amp;")}">Qué es RAG</a>'


def test_markdown_link_and_snake_case_left_alone():
    html = to_telegram_html("See [docs](https://example.com/a_b) for my_var_name", "V")
    assert html == 'See <a href="https://example.com/a_b">docs</a> for my_var_name'
