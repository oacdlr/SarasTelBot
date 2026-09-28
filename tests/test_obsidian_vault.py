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


def _titles(notes):
    return [n.title for n in notes]


def test_related_ignores_generic_title_words(vault):
    obsidian_vault.write_note("Discovery", "Guía para preparar café", "Molienda gruesa.", ["coffee"])
    assert obsidian_vault.find_related("Guía para ser Project Manager", limit=3) == []


def test_related_finds_notes_sharing_a_specific_topic(vault):
    obsidian_vault.write_note("Discovery", "Asymptotic Notation", "Growth rates.", ["big-o-notation"])
    obsidian_vault.write_note("Discovery", "Guía para preparar café", "Molienda gruesa.", ["coffee"])
    found = obsidian_vault.find_related("Understanding Big O Notation asymptotic big-o-notation")
    assert _titles(found) == ["Asymptotic Notation"]


def test_related_needs_more_than_a_body_mention(vault):
    obsidian_vault.write_note("Discovery", "Meal planning", "Sometimes I read about docker and coffee.", [])
    assert obsidian_vault.find_related("Docker containers") == []


def test_related_single_word_must_be_in_the_title_not_an_alias(vault):
    path = obsidian_vault.write_raw_note(
        "Concepts", "Grafo de estados",
        '---\ntitle: "Grafo de estados"\naliases: ["State Graph"]\ntags: [concept]\n---\n\nText\n',
    )
    assert obsidian_vault.find_related("Assumption of State Debts") == []
    obsidian_vault.write_note("Discovery", "Hamilton and the state debts", "Body", [])
    assert _titles(obsidian_vault.find_related("Hamilton")) == ["Hamilton and the state debts"]
    assert path  # the alias-only note was a real candidate


def test_related_skips_plans_quizzes_and_templates(vault):
    obsidian_vault.write_note("Execution", "Docker migration plan", "- [ ] step", ["execution"])
    obsidian_vault.write_note("Quizzes", "Docker migration quiz", "Q1", ["quiz"])
    obsidian_vault.write_note("templates", "Docker migration template", "x", [])
    obsidian_vault.write_note("Discovery", "Docker migration notes", "Body", [])
    assert _titles(obsidian_vault.find_related("Docker migration")) == ["Docker migration notes"]


def test_related_respects_exclude_and_limit(vault):
    topic = "Rust programming rust memory-safety"
    for name in ("Rust ownership", "Rust borrowing", "Rust lifetimes", "Rust traits"):
        obsidian_vault.write_note("Discovery", name, "Body", ["memory-safety"])
    assert len(obsidian_vault.find_related(topic, limit=10)) == 4
    assert len(obsidian_vault.find_related(topic, limit=3)) == 3
    without = obsidian_vault.find_related(topic, exclude={"rust traits"}, limit=10)
    assert "Rust traits" not in _titles(without) and len(without) == 3


def test_related_one_common_word_is_not_enough(vault):
    for name in ("Rust ownership", "Rust borrowing", "Rust lifetimes", "Rust traits"):
        obsidian_vault.write_note("Discovery", name, "Body", [])
    assert obsidian_vault.find_related("Rust async") == []
