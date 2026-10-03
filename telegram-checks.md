# Telegram checks: optional

Last updated: 2026-10-02

Optional checks on Telegram for the 2026-10-02 changes (review items 3.4, 2.1, 2.2, 2.4).
The bot must be running the current code. If a check fails, the bot log usually shows why.

- [ ] **Answer buttons don't rewrite the topic again**
  1. Send `Explícame qué es Docker`, then `¿y cómo se compara con las máquinas virtuales?`
  2. Under the answer, tap **🔍 Más detalle**.
  3. Expected: the detail is about Docker vs. VMs, with no drift to another topic. The log shows one `Mode: detail` line.

- [ ] **Quiz works on a topic you've quizzed before**
  1. Send `/quiz RAG` twice.
  2. Expected: both runs ask questions about your RAG notes, and the second doesn't say "Nothing in the Vault".
  3. In Obsidian, the new note in `Quizzes/` has `type: quiz` in its frontmatter.

- [ ] **Plan notes get a type**
  1. Send `/plan preparar una presentación`.
  2. Expected: the new note in `Execution/` has `type: execution` in its frontmatter.

- [ ] **Recall ignores notes that only mention a word in passing**
  1. Send `/recall RAG`. Expected: it answers from your RAG notes, as before.
  2. Send `/recall` with something you only mentioned in passing and never researched.
     Expected: "I don't have anything on that in the Vault yet", not a weak answer.
