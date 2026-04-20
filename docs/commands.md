# Commands Reference

Every command orai provides, with all arguments and options.

---

## `orai install`

Add a global alias so you can run `orai` from anywhere.

```bash
orai install
```

Detects your shell and appends an alias to the appropriate config file:

| Shell | Config file |
|-------|-------------|
| bash  | `~/.bashrc` |
| zsh   | `~/.zshrc` |
| fish  | `~/.config/fish/config.fish` |

Running this command again is safe. It skips if the alias already exists.

---

## `orai init`

Create a new project with a ready-to-use directory structure.

```bash
orai init <name> [OPTIONS]
```

| Argument | Required | Description |
|----------|----------|-------------|
| `name`   | Yes      | Project name (used as directory name) |

| Option | Default | Description |
|--------|---------|-------------|
| `-t`, `--template` | `nextjs` | Project template: `nextjs`, `python`, `node`, or `go` |
| `-p`, `--path` | `.` (current directory) | Parent directory where the project is created |

**Examples:**

```bash
orai init myapp
orai init myapp -t python
orai init myapp -t nextjs -p ~/projects
```

---

## `orai plan`

Run an interactive planning session. Metatien interviews you about your project requirements, scans the existing codebase for context, then uses Claude (Opus) to generate a phased implementation plan.

```bash
orai plan <project> [OPTIONS]
```

| Argument | Default | Description |
|----------|---------|-------------|
| `project` | `.` | Path to project root |

| Option | Default | Description |
|--------|---------|-------------|
| `--interactive` / `--auto` | `--interactive` | Use interactive interview mode |

**What happens during planning:**

1. You answer questions about features, auth, database, API, and phase count
2. Metatien scans the project and generates a context document (`app/.agents/CONTEXT.md`)
3. Claude (Opus) decomposes requirements into phases with ordered, dependency-aware tasks
4. Each task is assigned an `agent_role` (architect, project_manager, backend, frontend, tester) and `context_documents` (KB paths to read)
5. Phase files are saved to `app/.agents/tasks/phase1.json`, `phase2.json`, etc.

Optionally provide a product spec file to guide planning:

```bash
orai plan myapp --spec PRODUCT.md
```

---

## `orai run`

Execute tasks by invoking the Claude CLI for each one.

```bash
orai run <project> [OPTIONS]
```

| Argument | Default | Description |
|----------|---------|-------------|
| `project` | `.` | Path to project root |

| Option | Default | Description |
|--------|---------|-------------|
| `--phase <N>` | (all phases) | Run only phase N |
| `--task <ID>` | (all tasks) | Run a single task by ID (e.g., `2.3`) |
| `--resume` | `false` | Clear pause state and resume execution |
| `--dry-run` | `false` | Print commands without executing them |

**Execution behavior:**

- Tasks run one at a time, in priority order
- A task only starts when all its dependencies (`depends_on`) are complete
- State is saved after every task, so you can stop and resume safely
- Each task runs with a 600-second timeout

**Stopping execution:**

| Action | What happens |
|--------|-------------|
| `Ctrl+C` (once) | Finishes the current task, saves state, exits |
| `Ctrl+C` (twice) | Force quit immediately |
| `orai pause` | Stops after current task (from another terminal) |

**Examples:**

```bash
orai run myapp
orai run myapp --phase 2
orai run myapp --task 2.3
orai run myapp --resume
orai run myapp --dry-run
```

---

## `orai status`

Show a progress table for all phases and tasks.

```bash
orai status <project>
```

| Argument | Default | Description |
|----------|---------|-------------|
| `project` | `.` | Path to project root |

**Output includes:**

- Each phase with title and completion count
- Each task with ID, status, model, and description
- Overall completion summary

**Status colors:**

| Status | Color |
|--------|-------|
| pending | dim |
| running | yellow |
| done | green |
| failed | red |
| paused | yellow |
| skipped | dim |

---

## `orai pause`

Request a graceful pause. The runner stops after the current task finishes.

```bash
orai pause <project>
```

| Argument | Default | Description |
|----------|---------|-------------|
| `project` | `.` | Path to project root |

To resume after pausing:

```bash
orai run myapp --resume
```

---

## `orai reset`

Reset tasks back to `pending` status so they can be re-run.

```bash
orai reset <project> [OPTIONS]
```

| Argument | Default | Description |
|----------|---------|-------------|
| `project` | `.` | Path to project root |

| Option | Description |
|--------|-------------|
| `--task <ID>` | Reset a specific task (e.g., `2.3`) |
| `--phase <N>` | Reset all tasks in phase N |

You must specify either `--task` or `--phase`.

**Examples:**

```bash
orai reset myapp --task 2.3
orai reset myapp --phase 2
```

---

## `orai agents`

List all configured agents in the project.

```bash
orai agents <project>
```

| Argument | Default | Description |
|----------|---------|-------------|
| `project` | `.` | Path to project root |

Displays a table with each agent's name, role, language stack, email, skills, scripts, and model.

---

## `orai agents add`

Interactively add a new agent to the project.

```bash
orai agents add <project>
```

| Argument | Default | Description |
|----------|---------|-------------|
| `project` | `.` | Path to project root |

Prompts you for 7 fields (6 for non-backend roles):

| Field | Required | Description |
|-------|----------|-------------|
| Name | Yes | Agent name (e.g., "DevOps Engineer") |
| Email | Yes (has default) | Git author email, defaults to `{name-slug}@project.local` |
| Role | Yes | `architect`, `project_manager`, `backend`, `frontend`, or `tester` |
| Language stack | (backend only) | `python`, `node`, or `go` |
| Skills | No | Comma-separated skill names (match `## sections` in Skills.md) |
| Scripts | No | Comma-separated script names (match `### entries` in Skills.md) |
| Model | Yes (has default) | `haiku`, `sonnet`, or `opus` (default: `sonnet`) |

After adding the agent, orai checks if Skills.md has sections for each skill. If a skill section is missing, you can add it right there — Skills.md is a Markdown file, so you type or paste content in Markdown format.

See the [Agents Guide](./agents.md) for more details.

---

## `orai report`

Show a comprehensive project report including plan, progress, problems, and document graph status.

```bash
orai report <project>
```

| Argument | Default | Description |
|----------|---------|-------------|
| `project` | `.` | Path to project root |

**Output includes:**

- **Project Overview** — Name, type, created date, current phase
- **Progress Bar** — Overall percentage with done/failed/running/pending counts
- **Problems Panel** — Failed tasks with error previews (if any)
- **Phase Summary** — Table of all phases with done/failed/pending counts and next actionable task
- **Document Graph** — List of all KB documents, their titles, and which task produced them

**Example output:**

```
╭────────────────────────────── Project Overview ──────────────────────────────╮
│ myapp (python)                                                               │
│ Created: 2026-04-20 15:00 UTC                                                │
│ Current phase: 2                                                             │
╰──────────────────────────────────────────────────────────────────────────────╯

Progress: 66% (4/6 done, 0 failed, 0 running, 2 pending)
No problems detected.

┏━━━━━━━┳━━━━━━━━━━━━━━┳━━━━━━┳━━━━━━━━┳━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Phase ┃ Title        ┃ Done ┃ Failed ┃ Pending ┃ Next Task                     ┃
┡━━━━━━━╇━━━━━━━━━━━━━━╇━━━━━━╇━━━━━━━━╇━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ 1     │ Architecture │ 2    │        │ 0       │ (none)                        │
│ 2     │ Core Features│ 2    │        │ 2       │ 2.1: Implement user model     │
│ 3     │ Testing      │ 0    │        │ 2       │ 3.1: Review user API          │
└───────┴──────────────┴──────┴────────┴─────────┴───────────────────────────────┘

Document Graph: 3 document(s)
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━┓
┃ Path                            ┃ Title               ┃ Produced By  ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━┩
│ architecture/ARCHITECTURE.md    │ System Architecture │ 1.1          │
│ architecture/tech-stack.md      │ Tech Stack          │ 1.2          │
│ task-outputs/task-2.1-output.md │ Task 2.1 output     │ 2.1          │
└─────────────────────────────────┴─────────────────────┴──────────────┘
```
