# Metatien Documentation

Welcome to the orai documentation. These guides cover everything you need to install, configure, and use orai to build software with AI agents.

---

## Guides

| Guide | Description |
|-------|-------------|
| [Getting Started](./getting-started.md) | Install, create a project, plan with an AI team, run the full flow |
| [Commands Reference](./commands.md) | Every command with all arguments and options |
| [Agents Guide](./agents.md) | Multi-agent team roles, skills, document graph, KB system |
| [Project Structure](./project-structure.md) | Every file and directory orai creates |
| [How It Works](./how-it-works.md) | Technical details of the orchestration engine and document graph |

---

## Quick start

```bash
# Install
git clone https://github.com/tienmr/orai.git
cd orai && uv venv && uv pip install -e .
.venv/bin/orai install

# Create a project with 5 pre-configured agents
orai init myapp -t python

# Plan it — AI decomposes into phases for architect, PM, backend, frontend, tester
orai plan myapp

# Review the plan
orai report myapp

# Build it — AI team executes tasks
orai run myapp

# Check progress
orai status myapp
orai report myapp
```

---

## Support

For questions, bug reports, and feature requests, please open an issue on the [GitHub repository](https://github.com/tienmr/orai/issues).
