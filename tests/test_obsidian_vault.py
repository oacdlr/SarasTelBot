from saras.integrations import obsidian_vault


def test_write_and_search_note(vault):
    path = obsidian_vault.write_note("Discovery", "Test Note", "Some body text", ["test"])
    assert "Some body text" in open(path, encoding="utf-8").read()
    results = obsidian_vault.search_notes("body text")
    assert [n.path for n in results] == [path]


def test_title_with_windows_invalid_chars(vault):
    path = obsidian_vault.write_note("Discovery", 'What is "RAG"? A/B: test*', "body", [])
    assert obsidian_vault.note_title(path) == "What is RAG A B test"


def test_never_overwrites_existing_note(vault):
    first = obsidian_vault.write_note("Discovery", "Docker", "one", [])
    second = obsidian_vault.write_note("Discovery", "Docker", "two", [])
    assert first != second
    assert "one" in open(first, encoding="utf-8").read()


def test_frontmatter_includes_sources(vault):
    path = obsidian_vault.write_note("Discovery", "RAG", "body", ["discovery"], sources=["Site - https://x.y"])
    content = open(path, encoding="utf-8").read()
    assert content.startswith("---\ntitle: \"RAG\"")
    assert "tags: [discovery]" in content
    assert '  - "Site - https://x.y"' in content


def test_search_uses_keywords_not_whole_message(vault):
    obsidian_vault.write_note("Discovery", "Transformers", "Attention is all you need.", ["discovery"])
    obsidian_vault.write_note("Discovery", "Docker", "Containers.", ["discovery"])
    results = obsidian_vault.search_notes("What did I learn about transformers last month?")
    assert [n.title for n in results] == ["Transformers"]


def test_search_is_accent_insensitive(vault):
    obsidian_vault.write_note("Discovery", "Atención", "Mecanismo de atención", [])
    assert obsidian_vault.search_notes("atencion")[0].title == "Atención"
