# How It Works

A technical overview of what orai does under the hood at each stage.

---

## The big picture

Metatien is an orchestrator. It does not write code itself. Instead, it breaks your project into small, well-defined tasks and hands each one to Claude Code CLI (`claude`) with the right context, model, and instructions. Think of it as a project manager that delegates to a team of AI developers.

```
You (human)
  |
  |  orai init myapp -t python
  v
Project scaffold: agents (5 roles), KB structure, Skills.md, templates
  |
  |  orai plan myapp
  v
Interview --> Context Scan --> AI Decomposition --> Phase/Task JSONs
                                                       |
  |  orai run myapp                                  |
  v                                                   v
Phase 1: Architect (opus) ─── writes ─── kb/architecture/
                                       |
Phase 2: PM (opus) ─── reads arch ─── creates implementation tasks
                                       |
Phase 3+: Backend/Sonnet ─── reads KB ─── writes code + task outputs
         Frontend/Sonnet ─── reads KB ─── writes UI + task outputs
         Tester/Sonnet ─── reads outputs ─── reports bugs
                                       |
                                       v
                              Working application
```

---

## Stage 1: Project initialization

`orai init` uses Jinja2 templates to render a project scaffold.

1. Loads `structure.json` from the template directory (e.g., `scaffold/templates/python/`)
2. Creates all directories listed in the manifest, including the KB structure (`kb/architecture/`, `kb/phases/`, `kb/agent-contexts/`, `kb/shared/`, `kb/task-outputs/`)
3. Renders each template file (`.j2`) with the project name and type
4. Creates `project.json` metadata in `app/.agents/`
5. Creates `agents.json` with all 5 agent roles
6. Creates `orchestration.json` with project settings
7. Creates `kb/_index.json` (empty document graph index)

Available templates: `nextjs`, `python`, `node`, `go`.

---

## Stage 2: Planning

`orai plan` has three steps:

### Step 2a: Interview

An interactive questionnaire collects:

| Question | Purpose |
|----------|---------|
| Project description | High-level goal for the AI architect |
| Feature list | Concrete deliverables to plan around |
| Auth type | Determines auth-related tasks |
| Database type | Determines data layer tasks |
| API exposure | Determines if API routes are needed |
| Phase count | How many phases to split work into (2-5) |
| Extra requirements | Anything else the AI should know |

### Step 2b: Context generation

Before sending requirements to Claude, orai scans the project to build a context document (`CONTEXT.md`). This document tells the AI architect (and later, the executing agents) what already exists.

The scan detects:

| What | How |
|------|-----|
| Tech stack | Parses `package.json`, `pyproject.toml`, and similar config files |
| Directory structure | Walks the file tree (max 4 levels deep, ignoring `node_modules`, `.git`, etc.) |
| Key documentation | Reads the first 80 lines of `CLAUDE.md`, `README.md`, `ARCHITECTURE.md` |
| Config files | Reads the first 50 lines of `package.json`, `pyproject.toml`, etc. |
| Entry points | Finds files matching patterns like `src/**/main.*`, `app/layout.*`, `src/**/routes.*` |

### Step 2c: AI decomposition

Metatien calls the Claude CLI with the Opus model:

```bash
claude --print \
  --model opus \
  --output-format json \
  --max-turns 15 \
  -    # reads prompt from stdin
```

The system prompt instructs Claude to:

- **Phase 1 MUST be architecture** — tasks assigned to the `architect` role that produce KB documents
- **Phase 2 MUST be task breakdown** — tasks assigned to the `project_manager` role
- **Remaining phases are implementation** — tasks assigned to `backend`, `frontend`, or `tester` roles
- Set `agent_role` for every task (not just `target_model`)
- Set `context_documents` — specific KB paths each task should read
- Set `depends_on` — task IDs from earlier phases
- Set priorities (1 = most urgent)
- Write complete task prompts that reference specific KB documents

Each task in the output has:

```json
{
  "id": "3.1",
  "description": "Implement login API endpoint",
  "prompt": "Create POST /api/auth/login endpoint...",
  "priority": 1,
  "agent_role": "backend",
  "context_documents": [
    "architecture/ARCHITECTURE.md",
    "architecture/tech-stack.md"
  ],
  "depends_on": ["2.1"],
  "tdd_required": true
}
```

The output is validated against the schema and saved as `phase1.json`, `phase2.json`, etc.

---

## Stage 3: Execution

`orai run` processes tasks one at a time.

### Task selection

For each phase, orai picks the next task by:

1. Filtering to `pending` tasks only
2. Checking that all `depends_on` tasks are `done`
3. Sorting by priority (1 = highest)
4. Running the first match

Dependencies may reference tasks in earlier phases, so orai loads all prior phase files to resolve cross-phase dependencies.

### Agent resolution

Tasks can specify an agent two ways:

1. **`target_agent`** — Direct agent name (e.g., `"Frontend Developer"`). Resolved by name lookup in `agents.json`.
2. **`agent_role`** — Role string (e.g., `"backend"`). Resolved by finding the agent with that role in `agents.json`.

### System prompt construction (v2)

When a task has `agent_role`, the system prompt is built from four parts:

```
1. Role-specific template (from src/orai/prompts/{template}.md.j2)
   "You are Backend Developer <backend@myapp.local>.
    Your stack: FastAPI + Pydantic + Alembic + uv.
    Your workflow: Read architecture docs, write tests first, implement..."

2. Task-specific KB documents (from task.context_documents)
   "## Reference: architecture/ARCHITECTURE.md
    [content of the file]"

3. Architecture document (for non-architect agents, first 3000 chars)
   "## Architecture
    [first 3000 chars of ARCHITECTURE.md]"

4. Filtered Skills.md (only ## sections matching agent.skills)
   "## Available Skills and Scripts
    [relevant skill documentation]"
```

This targeted approach means each agent sees only the documents it needs — typically 500-1500 tokens vs the full CONTEXT.md at 2000+ tokens.

### Claude CLI invocation

Each task runs as a subprocess:

```bash
claude --print \
  --model {haiku|sonnet|opus} \
  --max-turns 50 \
  --permission-mode auto \
  --allowedTools "Bash,Edit,Read,Write,Glob,Grep" \
  --system-prompt "<prompt>" \
  "<task instruction>"
```

| Flag | Purpose |
|------|---------|
| `--print` | Stream output to stdout |
| `--model` | AI model for this task (from the agent's `model` field) |
| `--max-turns 50` | Allow up to 50 tool-use turns |
| `--permission-mode auto` | Auto-approve file operations |
| `--allowedTools` | Restrict which tools the AI can use |
| `--system-prompt` | Agent identity + KB context + skills |

The working directory is set to `app/` so file paths in task prompts are relative to the application root.

### Post-task artifact capture

After a task completes successfully, orai writes a summary to the KB:

- `kb/task-outputs/task-{id}-output.md` — Task description, status, artifacts produced, output summary
- Updates `_index.json` to register the new document
- Scans the output for file mentions and updates `task.artifacts_produced`

This allows downstream agents (especially the tester) to read what was implemented.

### State management

After each task:

1. Status is updated (`done` or `failed`)
2. Timestamps are recorded (`started_at`, `completed_at`)
3. Output or error is captured (first 500 characters)
4. The phase JSON is saved to disk

This means execution can stop and resume at any point without losing progress.

### Tester feedback loop

After implementation phases complete, tester tasks run automatically. The tester:

1. Reads task outputs from `kb/task-outputs/`
2. Reviews the implemented code
3. Runs the test suite
4. Writes bug reports to `kb/task-outputs/bug-{id}.md` if issues are found

If critical or major bugs are found, new fix tasks are created and the original agents re-run those tasks. This loop repeats up to `max_retry_loops` (default: 3).

### Graceful shutdown

Metatien installs signal handlers for `SIGINT` (Ctrl+C) and `SIGTERM`:

- **First signal**: Sets a flag. The current task finishes normally. State is saved. Runner exits.
- **Second signal**: Force kills immediately (restores original signal handler).

You can also pause from another terminal with `orai pause`, which writes a sentinel file that the runner checks between tasks.

---

## Document Graph

The Knowledge Base (`kb/`) is a file-based document graph. Agents communicate through documents rather than direct messages.

### Index (`_index.json`)

A JSON array of document metadata:

```json
[
  {
    "path": "architecture/ARCHITECTURE.md",
    "title": "System Architecture",
    "description": "Overall system design and component relationships",
    "produced_by_task": "1.1",
    "consumed_by_roles": ["project_manager", "backend", "frontend", "tester"]
  }
]
```

The index tracks:
- Where each document lives
- Who created it (task ID)
- Which agent roles should read it

### Context Assembly

When building a task's context, orai reads `_index.json` to find documents relevant to the current task and agent role, then assembles only those documents into the system prompt.

### Benefits

1. **Token efficiency** — Agents read only what they need, not the full project context
2. **Inter-agent communication** — Agents write documents that other agents read
3. **Human visibility** — All KB documents are plain Markdown, readable and editable by humans
4. **Version control friendly** — Changes to architecture decisions appear as file diffs

---

## Model selection strategy

| Model | Cost | Speed | Use when |
|-------|------|-------|----------|
| Haiku | Lowest | Fastest | Creating files, writing configs, formatting, boilerplate |
| Sonnet | Medium | Balanced | Business logic, UI components, API routes, writing tests |
| Opus | Highest | Slowest | Architecture decisions, complex refactoring, system design, task breakdown |

Agent roles use fixed models by default:
- **architect** and **project_manager** always use Opus (complex reasoning)
- **backend**, **frontend**, and **tester** use Sonnet (balanced capability)
- Utility tasks without an agent role may use Haiku
