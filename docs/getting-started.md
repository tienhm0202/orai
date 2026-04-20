# Getting Started

This guide walks you through the complete flow: installing orai, creating a project, planning with an AI team, and executing tasks — from the very first step to a working application.

---

## Prerequisites

| Requirement | Version | Why |
|-------------|---------|-----|
| Python | 3.11 or later | Runtime for orai |
| [uv](https://docs.astral.sh/uv/) | Latest | Fast Python package manager |
| [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code) | Latest | The AI engine that executes tasks |

Verify your setup:

```bash
python3 --version    # Should print 3.11+
uv --version         # Should print a version number
claude --version     # Should print a version number
```

---

## Installation

### Step 1 — Clone the repository

```bash
git clone https://github.com/tienmr/orai.git
cd orai
```

### Step 2 — Create a virtual environment and install

```bash
uv venv
uv pip install -e .
```

### Step 3 — Make it available globally

```bash
.venv/bin/orai install
```

This detects your shell (bash, zsh, or fish) and adds an alias to your shell config file automatically. After running this, either restart your terminal or source your config:

```bash
# bash
source ~/.bashrc

# zsh
source ~/.zshrc

# fish
source ~/.config/fish/config.fish
```

### Verify installation

```bash
orai --help
```

You should see the list of available commands.

---

## The Complete Flow: From Zero to Working App

Here is the end-to-end process. Think of orai as setting up and managing an AI development team for your project.

### Step 1: Create the Project

Choose a template based on your preferred stack:

```bash
# Python backend + Next.js frontend (default)
orai init myapp -t python

# Node.js backend with Hono + Bun
orai init myapp -t node

# Go backend with Fiber
orai init myapp -t go

# Next.js full-stack (default)
orai init myapp -t nextjs
```

This creates a project with:
- Application source code (`app/src/`)
- Agent configurations (`app/.agents/agents.json`) — 5 pre-configured roles
- Skills documentation (`app/.agents/Skills.md`)
- Knowledge base structure (`app/.agents/kb/`) — where agents communicate
- Orchestration config (`app/.agents/orchestration.json`) — project settings

### Step 2: Plan the Project

```bash
orai plan myapp
```

You can optionally provide a product spec file to guide planning:

```bash
orai plan myapp --spec PRODUCT.md
```

The planning process has two steps:

**2a. Interview** — orai asks you questions:

```
Describe your project in 1-2 sentences:
> A task management app with team collaboration

List the main features (comma-separated):
> user auth, task boards, real-time updates, team invites

Does it need authentication? [y/N]: y
Auth type? [jwt/session/oauth/clerk/nextauth]: nextauth

Does it need a database? [y/N]: y
Which DB? [postgres/sqlite/mysql/mongo]: postgres

Does it expose an API? [Y/n]: y

How many phases? [2/3/4/5]: 3

Any other requirements?:
> Use Prisma ORM, deploy to Vercel
```

**2b. AI Decomposition** — orai sends your answers + project context to Claude (Opus). The AI:
1. Creates Phase 1: Architecture tasks assigned to the **Solution Architect** agent
2. Creates Phase 2: Task breakdown assigned to the **Project Manager** agent
3. Creates remaining phases: Implementation tasks for **Backend**, **Frontend**, and **Tester** agents

Each task includes:
- `agent_role` — which agent type handles it
- `context_documents` — which KB docs the agent should read (minimizes token usage)
- `depends_on` — task IDs that must complete first
- `priority` — execution order within the phase

The plan is saved as JSON files in `app/.agents/tasks/phase1.json`, `phase2.json`, etc.

### Step 3: Review the Plan

Before running, check what the AI planned:

```bash
orai report myapp
```

This shows:
- Project overview
- Progress percentage
- Phase summary with next actionable tasks
- Any problems (failed/blocked tasks)
- Document graph status (KB documents)

Or use the web UI for a visual dashboard:

```bash
orai ui myapp
```

### Step 4: Run the Plan

```bash
orai run myapp
```

Tasks execute sequentially. Each agent:
1. Receives a **role-specific system prompt** from `prompts/` templates
2. Reads only the **KB documents** relevant to its task (not the whole project)
3. Works within the `app/` directory
4. Outputs are captured to `app/.agents/kb/task-outputs/` for other agents to read

Progress displays live in the terminal. Controls:
- **Ctrl+C** — Finish current task, then stop gracefully
- **Ctrl+C again** — Force kill
- **orai pause myapp** — Pause from another terminal

To resume after interruption:

```bash
orai run myapp --resume
```

To run a single phase or task:

```bash
orai run myapp --phase 2
orai run myapp --task 2.1
```

To preview what would run without executing:

```bash
orai run myapp --dry-run
```

### Step 5: Monitor Progress

Check status at any time:

```bash
orai status myapp
```

Shows a table with task ID, status, agent role, and description:

```
myapp (python)

Phase 1: Architecture — 2/2 done
 ID    Status   Agent           Description
 1.1   done     architect       Write architecture document
 1.2   done     architect       Select tech stack

Phase 2: Task Breakdown — 0/5 pending
 ID    Status   Agent           Description
 2.1   pending  project_manager Define user model and auth flow
 2.2   pending  backend         Implement login API endpoint
 ...
```

For a detailed report:

```bash
orai report myapp
```

### Step 6: Iterate

If a task fails, you can:
1. Check the error in `orai status`
2. Fix the issue manually or edit the task prompt in `app/.agents/tasks/phaseN.json`
3. Reset the task: `orai reset myapp --task 2.3`
4. Re-run: `orai run myapp --resume`

---

## How the Agent Team Works Together

### Phase 1: Architecture (runs first, always)

The **Solution Architect** agent (Opus) produces:
- `kb/architecture/ARCHITECTURE.md` — System design overview
- `kb/architecture/tech-stack.md` — Technology decisions
- `kb/architecture/decisions/` — Architecture Decision Records (ADRs)

These documents become the reference that all other agents read.

### Phase 2: Task Breakdown

The **Project Manager** agent (Opus) reads the architecture docs and creates detailed implementation tasks with:
- Clear acceptance criteria
- TDD requirements (tests first)
- Specific KB documents each task should read
- Dependencies between tasks

### Phases 3+: Implementation

- **Backend** tasks implement APIs, models, and migrations
- **Frontend** tasks implement UI components and pages
- **Tester** tasks review completed work and report bugs

Agents communicate through the KB: when a backend agent finishes a task, its output is written to `kb/task-outputs/`. The tester reads these to know what needs checking.

---

## What's Next

- Read the [Commands Reference](./commands.md) for the full list of commands and options
- Read the [Agents Guide](./agents.md) to learn about agent roles, skills, and the document graph
- Read the [Project Structure](./project-structure.md) to understand every file orai creates
- Read [How It Works](./how-it-works.md) for the technical details of the orchestration engine
