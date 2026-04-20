# Agents Guide

Agents are specialized AI personas that orai assigns to tasks. Every project ships with a 5-agent team, each with a distinct role, responsibilities, and knowledge domain.

---

## Agent Roles

Every project starts with these 5 agents defined in `app/.agents/agents.json`:

| Role | Model | Responsibility |
|------|-------|----------------|
| **architect** | opus | System design, tech stack selection, architecture documents |
| **project_manager** | opus | Task breakdown, TDD enforcement, Definition of Done |
| **backend** | sonnet | API, models, migrations (Python/Node/Go as chosen by architect) |
| **frontend** | sonnet | Next.js UI, components, pages |
| **tester** | sonnet | Code review, test execution, bug reporting |

### Agent Fields

Each agent in `agents.json` has these fields:

```json
{
  "name": "Backend Developer",
  "email": "backend@myapp.local",
  "role": "backend",
  "language_stack": "python",
  "skills": ["backend-api", "database-migrations", "testing"],
  "scripts": ["run-tests.sh"],
  "model": "sonnet",
  "system_prompt_template": "backend-python"
}
```

| Field | Purpose |
|-------|---------|
| `name` | Human-readable name. Must be unique. Used as git author name. |
| `email` | Git author email. Used for commits this agent makes. |
| `role` | Agent type: `architect`, `project_manager`, `backend`, `frontend`, `tester`. Determines which system prompt template is used. |
| `language_stack` | For backend agents only: `python`, `node`, or `go`. Determines the framework, ORM, migration tool, and testing framework. |
| `skills` | Comma-separated list matching `##` sections in `Skills.md`. Controls which skill documentation the agent sees. |
| `scripts` | Comma-separated list matching `###` entries in skill sections. Controls which scripts the agent can run. |
| `model` | Claude model: `haiku`, `sonnet`, or `opus`. |
| `system_prompt_template` | Template filename (without `.md.j2`) from `src/orai/prompts/`. Defaults to the role value. |

---

## How Agents Receive Context

### The Old Way: Monolithic CONTEXT.md

Previously, every task received the full `CONTEXT.md` (~2000+ tokens) regardless of what the task needed. This wasted tokens and gave every agent the same broad context.

### The New Way: Document Graph (KB)

Now agents read only the documents relevant to their task through the Knowledge Base (`app/.agents/kb/`):

```
kb/
  _index.json                  # Graph index — lists all documents, who created them, who reads them
  architecture/                # Written by the Architect agent (Phase 1)
    ARCHITECTURE.md            # System design overview
    tech-stack.md              # Technology decisions
    decisions/                 # Architecture Decision Records (ADRs)
      001-language-choice.md
      002-auth-strategy.md
  phases/                      # Phase-specific briefs (~300-500 tokens each)
  agent-contexts/              # Role-specific context documents
    architect-context.md
    pm-context.md
    backend-context.md
    frontend-context.md
    tester-context.md
  shared/                      # Cross-cutting documents
    coding-standards.md
    tdd-guidelines.md
  task-outputs/                # Post-task summaries — how agents communicate
    task-1.1-output.md
    task-1.2-output.md
```

### How Context Is Injected Per Task

When a task has `agent_role` set, the system prompt is built from:

1. **Role-specific template** — A detailed prompt from `src/orai/prompts/{template}.md.j2` that describes the agent's role, stack, workflow, and rules
2. **Task-specific KB documents** — Only the files listed in the task's `context_documents` array
3. **Architecture document** — For non-architect agents, the first 3000 chars of `ARCHITECTURE.md`
4. **Filtered Skills.md** — Only the `##` sections matching the agent's skills

This means a backend task implementing an API endpoint sees:
- The backend developer prompt template (framework, testing rules)
- The architecture doc (what to build)
- The tech stack doc (what tools to use)
- NOT the frontend docs, NOT the full project tree

---

## Agent Communication Flow

Agents communicate through KB documents, not direct messaging:

```
Phase 1: Architect
  Writes → kb/architecture/ARCHITECTURE.md
  Writes → kb/architecture/tech-stack.md
  Writes → kb/architecture/decisions/*.md

Phase 2: Project Manager
  Reads → kb/architecture/ARCHITECTURE.md
  Creates → Implementation tasks with context_documents pointing to KB files

Phase 3+: Implementation
  Backend reads → kb/architecture/tech-stack.md
  Backend writes → kb/task-outputs/task-{id}-output.md

Phase 3+: Testing
  Tester reads → kb/task-outputs/task-{id}-output.md
  Tester writes → kb/task-outputs/bug-{id}.md (if bugs found)
```

---

## Managing Agents

### Listing Agents

```bash
orai agents myapp
```

Shows all configured agents with their roles, language stacks, skills, and models:

```
Agents — myapp

 Name                 Role                Email                    Skills            Model
 Solution Architect   architect           architect@myapp.local    architecture...   opus
 Project Manager      project_manager     pm@myapp.local           task-breakup...   opus
 Backend Developer    backend (python)    backend@myapp.local      backend-api...    sonnet
 Frontend Developer   frontend            frontend@myapp.local     frontend          sonnet
 Tester               tester              tester@myapp.local       testing, bug...   sonnet
```

### Adding an Agent

```bash
orai agents add myapp
```

The CLI walks you through 7 fields:

```
Add New Agent (7 fields)

[1/7] Agent name: DevOps Engineer
[2/7] Email [devops-engineer@project.local]:
[3/7] Role [architect/project_manager/backend/frontend/tester] (backend): tester
[4/7] Skills (comma-separated, match ## sections in Skills.md): testing, e2e, ci-cd
[5/7] Scripts (comma-separated, optional): run-tests.sh
[6/7] Model [haiku/sonnet/opus] (sonnet):
[7/7] Confirm? [Y/n]:
```

For backend agents, you'll also be asked about language stack:

```
[3/7] Role [architect/project_manager/backend/frontend/tester] (backend): backend
[4/7] Language stack [python/node/go] (python):
```

### Editing Agents

You can edit `app/.agents/agents.json` directly in any text editor. The file is plain JSON. After editing, changes take effect immediately on the next `orai run`.

### Removing an Agent

Edit `app/.agents/agents.json` and remove the agent's entry from the `agents` array.

---

## System Prompt Templates

Each agent role has a Jinja2 template in `src/orai/prompts/` that defines the system prompt:

| Template | Agent Role | Purpose |
|----------|------------|---------|
| `architect.md.j2` | architect | System design instructions, deliverables (ARCHITECTURE.md, tech-stack.md, ADRs) |
| `pm.md.j2` | project_manager | Task breakdown, TDD enforcement, feedback loop management |
| `backend-python.md.j2` | backend (Python) | FastAPI + Pydantic + Alembic + uv workflow |
| `backend-node.md.j2` | backend (Node) | Hono + Drizzle + Bun + Vitest workflow |
| `backend-go.md.j2` | backend (Go) | Fiber + golang-migrate + sqlc + testing workflow |
| `frontend.md.j2` | frontend | Next.js + Bun + Tailwind workflow |
| `tester.md.j2` | tester | Code review, bug reporting, test execution |

To customize how an agent behaves, edit its template. Variables like `{{ agent.name }}`, `{{ project_name }}`, and `{{ project_rules }}` are replaced at runtime.

---

## Skills.md

`Skills.md` is a Markdown file at `app/.agents/Skills.md` that documents skills and scripts available to agents.

### Format

```markdown
# Agent Skills Reference — myapp

## backend-api
Skills for implementing API routes and server-side logic.

### run-tests.sh
**Purpose**: Run the test suite.
**Usage**: `bun test` or `uv run pytest` depending on stack.
**Expected output**: Test summary. Exit code 0 on pass.

---

## frontend
Skills for building and testing the Next.js frontend.

### build.sh
**Purpose**: Build the production bundle.
**Usage**: `bun run build`
**Expected output**: Build output. Exit code 0 on success.
```

- `## skill-name` sections match the agent's `skills` field
- `### script-name` entries within skill sections match the agent's `scripts` field

### Adding Skills

During `orai agents add`, if you reference a skill that doesn't exist in Skills.md, orai offers to create the section.

You can also edit Skills.md directly at any time.

---

## Language Stacks

Backend agents support three language stacks, each with a complete toolchain:

### Python

| Component | Tool |
|-----------|------|
| Framework | FastAPI |
| Validation | Pydantic v2 |
| Migrations | Alembic |
| Package manager | uv |
| Testing | pytest |

### Node.js

| Component | Tool |
|-----------|------|
| Runtime | Bun |
| Framework | Hono |
| ORM | Drizzle ORM |
| Migrations | Drizzle Kit |
| Validation | Zod |
| Testing | Vitest |

### Go

| Component | Tool |
|-----------|------|
| Framework | Fiber v2 |
| Database | database/sql + sqlc |
| Migrations | golang-migrate |
| Testing | testing (stdlib) + testify |

The architect agent chooses the language stack during Phase 1. The backend agent's `language_stack` field is then set accordingly.
