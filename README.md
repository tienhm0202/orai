# orai

Meta-Agentic Project Orchestrator — a CLI tool that automates project scaffolding, phase-based planning, and task execution by orchestrating the `claude` CLI.

## Requirements

- Python 3.11+
- [uv](https://docs.astral.sh/uv/)
- [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code) (`claude` in PATH)

## Installation

**One-step setup (recommended):**

```bash
git clone https://github.com/tienmr/orai.git
cd orai
./scripts/setup.sh
```

This installs `uv` if missing, creates a virtual environment, installs the package, and configures the global alias.

**Manual installation:**

```bash
git clone https://github.com/tienmr/orai.git
cd orai
uv venv
uv pip install -e .
.venv/bin/orai install
```

This detects your shell (bash/zsh/fish) and adds an alias to the appropriate config file.

## Quick start

```bash
# 1. Create a project
orai init myapp -t python

# 2. Plan — answer questions, AI generates phased tasks for the team
orai plan myapp

# 3. Run — AI team executes each task
orai run myapp

# 4. Check progress
orai report myapp
```

## Commands

| Command | Description |
|---------|-------------|
| `orai install` | Add global shell alias |
| `orai init <name>` | Scaffold a new project (`-t nextjs`, `python`, `node`, or `go`) |
| `orai plan <project>` | Interview + AI decomposition into phases/tasks |
| `orai run <project>` | Execute tasks (`--phase`, `--task`, `--resume`, `--dry-run`) |
| `orai status <project>` | Show progress table with agent column |
| `orai report <project>` | Full report: progress %, problems, plan, document graph |
| `orai pause <project>` | Graceful pause after current task |
| `orai reset <project>` | Reset tasks to pending (`--task` or `--phase`) |
| `orai agents <project>` | List configured agents with roles |
| `orai agents add <project>` | Add a new agent with role and language stack |
| `orai context <project>` | Generate plan state summary |
| `orai ui <project>` | Launch web UI for live progress monitoring |

## Agent roles

Every project ships with a 5-agent team:

| Role | Model | Responsibility |
|------|-------|----------------|
| **architect** | opus | System design, tech stack selection, architecture documents |
| **project_manager** | opus | Task breakdown, TDD enforcement, Definition of Done |
| **backend** | sonnet | API, models, migrations (Python/Node/Go as chosen by architect) |
| **frontend** | sonnet | Next.js UI, components, pages |
| **tester** | sonnet | Code review, test execution, bug reporting |

## Model selection

Tasks are assigned to models based on complexity:

| Model | Use case |
|-------|----------|
| **Haiku** | Boilerplate, config files, formatting |
| **Sonnet** | Business logic, UI, API routes, tests |
| **Opus** | Architecture decisions, complex refactoring |

## Project templates

| Template | Stack |
|----------|-------|
| `nextjs` | Next.js (App Router) + TypeScript + Tailwind CSS |
| `python` | Python + FastAPI + Pydantic + Alembic + uv + pytest |
| `node` | Node.js + Hono + Drizzle ORM + Bun + Vitest |
| `go` | Go + Fiber + database/sql + sqlc + golang-migrate |

## Documentation

Full documentation is available in the [`docs/`](./docs/) directory:

- [Getting Started](./docs/getting-started.md) — Install, create a project, run the full flow
- [Commands Reference](./docs/commands.md) — Every command with all options
- [Agents Guide](./docs/agents.md) — Multi-agent team roles, skills, document graph
- [Project Structure](./docs/project-structure.md) — Every file orai creates
- [How It Works](./docs/how-it-works.md) — Technical overview of the orchestration engine

## License

All rights reserved. A license key is required for use.
