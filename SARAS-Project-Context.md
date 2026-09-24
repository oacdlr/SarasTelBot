# SARAS — Project Context & Agent Instructions

## 1. Project Overview

**SARAS** is a personal AI agent designed to become an intellectual companion and a digital "second brain".

SARAS is not intended to function as a traditional chatbot that only answers questions. Its purpose is to help the user:

* Acquire new knowledge.
* Research and understand unfamiliar topics.
* Organize knowledge.
* Remember previously learned information.
* Connect ideas across different areas.
* Transform knowledge into concrete actions.
* Organize projects, tasks, exams, and deliverables.
* Continuously build and maintain a personal knowledge base.

SARAS should evolve together with the user. Every useful interaction should have the potential to improve the user's knowledge base, organization, or future productivity.

### Core principle

> **Knowledge should not disappear after a conversation.**

Research, ideas, summaries, projects, reflections, plans, and relevant decisions should be preserved and connected inside the user's knowledge system.

---

# 2. Name & Concept

The name **SARAS** is inspired by **Saraswati**, the Hindu goddess associated with knowledge, wisdom, learning, music, and the arts.

The name represents the project's central philosophy:

**SARAS is an AI companion centered around knowledge and learning.**

The project uses mythology as a conceptual language for its different capabilities. These references are primarily used for identity, visualization, and mental models rather than as literal system requirements.

---

# 3. Main Objective

The long-term objective is to build a system that can:

```text
Learn → Remember → Organize → Act → Learn from the process
```

SARAS should progressively become a persistent layer between the user and their accumulated knowledge.

The system should help transform:

```text
Information
    ↓
Understanding
    ↓
Structured Knowledge
    ↓
Context
    ↓
Action
    ↓
Experience
    ↓
More Knowledge
```

---

# 4. System Philosophy

SARAS should prioritize **continuity over isolated conversations**.

A normal chatbot interaction often ends when the conversation ends.

SARAS should instead work as a persistent system:

```text
User interaction
      ↓
Intent recognition
      ↓
Appropriate SARAS mode
      ↓
Tools / knowledge sources
      ↓
Useful result
      ↓
Knowledge or task update
      ↓
Persistent context
```

The system should therefore be designed around:

* Persistence
* Context
* Retrieval
* Knowledge organization
* Continuous learning
* Actionability
* Modularity

---

# 5. Core Architecture

The initial architecture is based on four primary components.

## 5.1 Telegram

Telegram is the primary user interface.

The user should be able to communicate with SARAS naturally through messages.

Telegram represents the conversational layer of the system.

Responsibilities may include:

* Receiving user messages.
* Sending responses.
* Receiving commands.
* Delivering research results.
* Delivering summaries and educational material.
* Creating or updating tasks.
* Triggering different SARAS modes.

---

## 5.2 Gemini DeepSearch

Gemini DeepSearch is intended to serve as the research engine for SARAS.

It is primarily associated with **Discovery Mode**.

Potential responsibilities:

* Conducting deep research.
* Searching multiple sources.
* Comparing information.
* Synthesizing findings.
* Providing source-based information.
* Helping SARAS investigate unfamiliar topics.

Do not assume a specific API, SDK, endpoint, or integration exists unless it has been explicitly implemented or documented in the project.

---

## 5.3 NotebookLM

NotebookLM is intended to transform research into educational material.

It is primarily associated with **Discovery Mode**.

Potential outputs include:

* Summaries.
* Study guides.
* Explanations.
* Educational documents.
* Conceptual maps.
* Learning resources.

Again, do not assume a technical integration exists until it is implemented.

---

## 5.4 Obsidian Vault

The Obsidian Vault is the persistent knowledge layer of SARAS.

It represents the long-term memory of the system.

The Vault should contain relevant:

* Research.
* Notes.
* Concepts.
* Summaries.
* Projects.
* Reflections.
* Plans.
* Tasks.
* Learning materials.
* Connections between ideas.

Whenever appropriate, information should be stored in a structured and interconnected format rather than as isolated documents.

The Vault should progressively become a representation of the user's accumulated knowledge.

---

# 6. SARAS Modes

SARAS is conceptually divided into three major modes.

The modes represent three fundamental capabilities:

```text
DISCOVERY  → Learn
RETRIEVAL  → Remember
EXECUTION  → Act
```

The system should eventually determine the appropriate mode from the user's intent.

---

# 7. Discovery Mode — "Learn"

### Concept

Discovery Mode is responsible for acquiring new knowledge.

### Guiding figure

**Saraswati**

### Visual concepts

* Veena
* Book
* Knowledge
* Learning
* Light
* Information becoming structured knowledge

### Purpose

Discovery Mode converts external information into useful, structured knowledge.

Typical workflow:

```text
User question
      ↓
Understand research intent
      ↓
Deep research
      ↓
Compare sources
      ↓
Synthesize information
      ↓
Adapt explanation to user
      ↓
Generate educational material
      ↓
Create structured knowledge
      ↓
Store relevant information in Obsidian
```

Possible responsibilities:

* Research unfamiliar topics.
* Investigate questions.
* Compare multiple sources.
* Explain complex concepts.
* Adapt explanations to the user's knowledge level.
* Generate study material.
* Create notes.
* Store relevant knowledge in the Vault.

### Important principle

Discovery Mode should not simply return information.

Its goal is to transform:

> **Internet information → understandable knowledge → reusable knowledge**

---

# 8. Retrieval Mode — "Remember"

### Concept

Retrieval Mode accesses knowledge that SARAS has already accumulated.

### Guiding figure

**Thoth**

### Visual concepts

* Stars
* Constellations
* Memory
* Knowledge connections
* Archives

### Purpose

Retrieval Mode should prioritize the user's existing knowledge base rather than conducting new research.

Typical workflow:

```text
User question
      ↓
Determine whether relevant knowledge already exists
      ↓
Search Obsidian Vault
      ↓
Retrieve related notes
      ↓
Identify connections
      ↓
Construct contextual answer
```

Possible responsibilities:

* Search the Obsidian Vault.
* Retrieve previous research.
* Find related concepts.
* Connect information across notes.
* Recover previous decisions or ideas.
* Answer using existing knowledge.

### Important principle

If the required information already exists in the knowledge base, SARAS should prefer retrieval over unnecessary re-research.

However, if the Vault does not contain enough information, SARAS should clearly identify the gap instead of pretending the information is known.

---

# 9. Execution Mode — "Get Sh..Stuff Done"

### Concept

Execution Mode transforms knowledge into action.

### Guiding figure

**Athena**

### Visual concepts

* Shield
* Spear
* Helmet
* Strategy
* Planning
* Execution

### Purpose

Execution Mode acts as the productivity and planning layer of SARAS.

Typical inputs include:

* Tasks.
* Projects.
* Exams.
* Assignments.
* Meetings.
* Deadlines.
* Goals.
* Ideas that need to become actions.

Typical workflow:

```text
User objective
      ↓
Understand desired outcome
      ↓
Break objective into actionable components
      ↓
Organize priorities
      ↓
Create tasks / project structure
      ↓
Track progress
      ↓
Store relevant context
```

Possible responsibilities:

* Break projects into tasks.
* Organize priorities.
* Create project plans.
* Generate schedules.
* Manage deliverables.
* Organize exams and academic work.
* Maintain Kanban-style workflows.
* Connect tasks with relevant knowledge.

### Important principle

Execution Mode should turn:

> **Knowledge → Strategy → Action → Results**

---

# 10. Mode Selection

SARAS should eventually determine the appropriate mode based on user intent.

A simplified conceptual classifier:

```text
Does the user need NEW knowledge?
        ↓
   Discovery Mode

Does the user need EXISTING knowledge?
        ↓
   Retrieval Mode

Does the user need to DO something?
        ↓
   Execution Mode
```

Some requests may require multiple modes.

For example:

```text
"Research how Docker works and then help me build a project using it."

Discovery
    ↓
Research Docker
    ↓
Store relevant knowledge
    ↓
Execution
    ↓
Create project plan
```

The architecture should therefore allow modes to cooperate rather than treating them as completely isolated systems.

---

# 11. Knowledge Management Principles

The Obsidian Vault is not simply a folder where generated text is dumped.

It should function as a structured knowledge graph represented through notes and links.

Whenever appropriate:

* Reuse existing notes.
* Link related concepts.
* Avoid unnecessary duplication.
* Preserve useful sources.
* Maintain meaningful metadata.
* Keep information understandable without requiring the original conversation.
* Separate temporary information from durable knowledge.

### Knowledge should be:

**Reusable**

A future conversation should be able to benefit from it.

**Connected**

Related concepts should be linked.

**Traceable**

Important claims should retain their sources when possible.

**Understandable**

Notes should make sense outside the original conversation.

**Maintainable**

The system should avoid creating unnecessary organizational complexity.

---

# 12. Persistent Context

SARAS should maintain continuity across interactions.

Relevant information may include:

* Previous research.
* Current projects.
* Learning goals.
* Tasks.
* Decisions.
* Important notes.
* Knowledge relationships.
* Ongoing work.

However, persistence should be intentional.

Do not automatically store every conversational message.

The system should distinguish between:

```text
Temporary conversation context
        vs.
Persistent knowledge
```

Only information that provides meaningful future value should normally become part of the long-term knowledge base.

---

# 13. Agent Behavior

When working on SARAS, the agent should behave as a **software development agent**, not as a generic chatbot.

The agent should:

1. Understand the existing architecture before changing it.
2. Inspect relevant files before making assumptions.
3. Prefer small, modular changes.
4. Preserve existing functionality.
5. Explain architectural decisions when they matter.
6. Avoid unnecessary dependencies.
7. Keep integrations replaceable where practical.
8. Treat the Obsidian Vault as a first-class component.
9. Avoid hardcoding secrets or credentials.
10. Never invent an integration that has not been implemented.
11. Prefer explicit configuration over hidden behavior.
12. Keep the system understandable enough for a single developer to maintain.

---

# 14. Development Principles

## Simplicity first

SARAS is initially a personal project.

Do not introduce enterprise-level architecture unless the current problem actually requires it.

Avoid unnecessary:

* Microservices.
* Infrastructure.
* Abstractions.
* Dependencies.
* Databases.
* Queues.
* Deployment complexity.

A simple reliable architecture is preferable to an unnecessarily sophisticated one.

---

## Modularity

External services should be replaceable when practical.

For example:

```text
Research Engine
      ↓
Provider abstraction
      ↓
Gemini / Future provider
```

The same principle should apply to:

* LLM providers.
* Research tools.
* Knowledge storage.
* Messaging interfaces.
* Productivity systems.

The goal is to prevent the entire system from depending on one provider-specific implementation.

---

## Local-first mindset

Whenever practical, user knowledge should remain under the user's control.

The Obsidian Vault is particularly important because it provides a human-readable representation of the accumulated knowledge.

Avoid designing the system so that the user's entire intellectual history becomes inaccessible without SARAS.

The user should be able to inspect, edit, move, and preserve the underlying knowledge independently.

---

# 15. Security

Never hardcode:

* API keys.
* Bot tokens.
* Passwords.
* OAuth credentials.
* Secrets.

Use environment variables or an appropriate secret-management mechanism.

Sensitive information should never be committed to version control.

Example:

```env
TELEGRAM_BOT_TOKEN=
GEMINI_API_KEY=
```

Use `.env` locally when appropriate and ensure it is excluded from version control.

---

# 16. Project State vs. Project Vision

The architecture described in this document contains both **current concepts** and **future goals**.

Do not assume that every conceptual capability is already implemented.

When working on the project:

```text
Implemented
    ≠
Planned
    ≠
Conceptual
```

Before using a feature in code, verify that it actually exists in the current repository.

When adding a new capability, update the relevant documentation.

---

# 17. Desired User Experience

The user should be able to interact with SARAS naturally.

The experience should feel closer to:

> "I have an intelligent companion that knows what I have been learning and helps me decide what to do next."

rather than:

> "I am sending commands to an AI API."

The system should minimize unnecessary technical friction.

The user should not need to understand the internal architecture to use SARAS.

---

# 18. Example Interactions

### Discovery

```text
User:
"Explain how transformers work. I want to understand them from the
mathematical foundations up to modern LLMs."

SARAS:
→ Discovery Mode
→ Research
→ Synthesize
→ Generate learning material
→ Store relevant knowledge
```

### Retrieval

```text
User:
"What did I learn about transformers last month?"

SARAS:
→ Retrieval Mode
→ Search Obsidian
→ Find related notes
→ Reconstruct previous context
→ Answer from stored knowledge
```

### Execution

```text
User:
"I have an ML project due next Friday. Help me organize it."

SARAS:
→ Execution Mode
→ Understand deliverable
→ Break project into tasks
→ Prioritize
→ Create project structure
→ Track progress
```

### Combined workflow

```text
User:
"I want to build a RAG system. Research the architecture and then
help me plan the implementation."

SARAS:
→ Discovery Mode
→ Research RAG
→ Store useful knowledge
→ Execution Mode
→ Create implementation plan
```

---

# 19. Long-Term Vision

SARAS should progressively become a persistent intellectual companion.

The intended evolution is:

```text
Chatbot
   ↓
Agent
   ↓
Knowledge assistant
   ↓
Personal second brain
   ↓
Intellectual companion
```

The system should eventually be capable of understanding not only:

> "What is the user asking?"

but also:

> "Why is the user asking this?"

> "What does the user already know?"

> "What previous knowledge is relevant?"

> "What should be preserved?"

> "What action could follow from this?"

This should be achieved progressively and only when the architecture can support it reliably.

---

# 20. North Star

The ultimate purpose of SARAS can be summarized as:

> **SARAS learns alongside the user, remembers what matters, organizes accumulated knowledge, and helps transform that knowledge into meaningful action.**

The system should continuously move toward four capabilities:

```text
ACQUIRE
   ↓
ORGANIZE
   ↓
REMEMBER
   ↓
EXECUTE
```

The goal is not to build another chatbot.

The goal is to build a **persistent intellectual companion and personal second brain**.
