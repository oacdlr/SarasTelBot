import os

from saras.integrations import obsidian_vault


def test_write_and_search_note(vault):
    path = obsidian_vault.write_note("Discovery", "Test Note", "Some body text", ["test"])
    assert "Some body text" in open(path, encoding="utf-8").read()
    results = obsidian_vault.search_notes("body text")
    assert [n.path for n in results] == [path]


def test_title_with_windows_invalid_chars(vault):
    path = obsidian_vault.write_note("Discovery", 'What is "RAG"? A/B: test*', "body", [])
    assert obsidian_vault.note_title(path) == "What is RAG A B test"


def test_delete_note_removes_the_file(vault):
    path = obsidian_vault.write_note("Discovery", "Docker", "body", [])
    assert obsidian_vault.delete_note(path) is True
    assert not os.path.exists(path)


def test_delete_note_missing_file_returns_false(vault):
    assert obsidian_vault.delete_note(str(vault / "Discovery" / "Nope.md")) is False


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


def _hub(title, question):
    return obsidian_vault.write_raw_note(
        "Discovery", title, f'---\ntitle: "{title}"\ntype: discovery\nquestion: "{question}"\n---\n\nBody.\n'
    )


def test_find_discovery_hub_matches_same_topic_by_question_or_title(vault):
    docker = _hub("Fundamentos y funcionamiento de Docker", "Explícame qué es Docker")
    rag = _hub("Guía de RAG", "¿Qué sabes de rag?")
    assert obsidian_vault.find_discovery_hub("Qué es docker y cómo funciona") == docker
    assert obsidian_vault.find_discovery_hub("Explain RAG") == rag  # via the question
    assert obsidian_vault.find_discovery_hub("Fundamentos de Docker") == docker  # via the title


def test_find_discovery_hub_ignores_narrower_or_other_topics(vault):
    _hub("Fundamentos de Docker", "Explícame qué es Docker")
    assert obsidian_vault.find_discovery_hub("Explícame Docker networking") is None
    assert obsidian_vault.find_discovery_hub("Explícame qué es Kubernetes") is None
    assert obsidian_vault.find_discovery_hub("Explícame") is None  # no topic words at all


def test_find_discovery_hub_without_discovery_folder(vault):
    assert obsidian_vault.find_discovery_hub("Explícame qué es Docker") is None


def test_search_skips_templates_by_default(vault):
    obsidian_vault.write_note("templates", "Docker template", "Docker placeholder.", [])
    note = obsidian_vault.write_note("Discovery", "Docker", "Docker runs containers.", [])
    assert [n.path for n in obsidian_vault.search_notes("docker")] == [note]
    assert len(obsidian_vault.search_notes("docker", skip=())) == 2


def test_relevance_leaves_out_the_recency_boost(vault):
    obsidian_vault.write_note("Discovery", "Meal planning", "I mention docker once.", [])
    [note] = obsidian_vault.search_notes("docker")
    assert note.relevance == 1.1  # one body hit
    assert note.score > 2.0  # written today, so the boost pushes it past MIN_SCORE


def test_write_note_type_goes_in_frontmatter(vault):
    path = obsidian_vault.write_note("Execution", "Plan", "- [ ] step", ["execution"], note_type="execution")
    lines = open(path, encoding="utf-8").read().splitlines()
    assert lines[:3] == ["---", 'title: "Plan"', "type: execution"]
    plain = obsidian_vault.write_note("Discovery", "Plain", "x", [])
    assert "type:" not in open(plain, encoding="utf-8").read()


def test_concept_index_prefers_a_filename_over_another_notes_alias(vault):
    alias_owner = obsidian_vault.write_raw_note("Concepts", "Aardvark", '---\naliases: ["Docker"]\n---\n\nx')
    named = obsidian_vault.write_raw_note("Concepts", "Docker", "---\n---\n\nx")
    index = obsidian_vault.concept_index()
    assert index["docker"] == named
    assert index["aardvark"] == alias_owner


def test_upsert_concept_adds_new_notes_to_a_shared_index(vault):
    index = obsidian_vault.concept_index()
    first = obsidian_vault.upsert_concept("Contenedor", ["Container"], "---\n---\n\nnew", "Aparece en", "- [[A]]", index=index)
    second = obsidian_vault.upsert_concept("Container", [], "---\n---\n\nother", "Aparece en", "- [[A]]", index=index)
    assert second == first  # matched through the alias of a note created earlier in the same run
    assert len(os.listdir(os.path.join(vault, "Concepts"))) == 1
