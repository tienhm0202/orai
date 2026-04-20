from __future__ import annotations

import json
import subprocess
import textwrap
from pathlib import Path

from orai.models import Phase, AgentRole


MULTI_AGENT_DECOMPOSITION_SYSTEM_PROMPT = """\
You are a lead software architect planning work for a multi-agent development team.
Given project requirements and existing project context, decompose them into
implementation phases with ordered tasks assigned to specific agent roles.

## Available Agent Roles
- **architect** (opus): Solution Architect. Produces architecture documents, tech stack decisions, and Architecture Decision Records (ADRs). ALWAYS runs as Phase 1.
- **project_manager** (opus): Project Manager. Breaks work into small, clear units with TDD enforcement and clear Definition of Done. Reads architect documents before planning.
- **backend** (sonnet): Backend Developer. Implements APIs, data models, migrations, and business logic. Language stack (Python FastAPI/Alembic, Node.js Hono+Drizzle, or Go Fiber+golang-migrate) is determined by the architect.
- **frontend** (sonnet): Frontend Developer. Next.js with Bun. Implements UI components, pages, and client-side logic.
- **tester** (sonnet): Tester. Reviews completed implementations, runs tests, reports bugs back to the Project Manager for reassignment.

## Document Graph (Agent Communication)
Agents communicate through documents under .agents/kb/. This is how information flows:
- Architecture docs (.agents/kb/architecture/) are written by the architect, read by all agents
- Phase briefs (.agents/kb/phases/) give targeted context per phase (~300-500 tokens)
- Agent contexts (.agents/kb/agent-contexts/) contain role-specific instructions and conventions
- Task outputs (.agents/kb/task-outputs/) summarize what each task produced
- Shared docs (.agents/kb/shared/) contain cross-cutting standards (TDD, coding conventions)

## Task Planning Rules
1. **Phase 1 MUST be architecture** with agent_role "architect". The architect produces:
   - ARCHITECTURE.md (system design overview)
   - tech-stack.md (chosen language and frameworks)
   - ADRs in decisions/ (architecture decision records)
2. **Phase 2 MUST be task breakdown** with agent_role "project_manager". The PM creates detailed implementation tasks with clear acceptance criteria.
3. **Remaining phases are implementation** with appropriate agent_role per task.
4. **Set agent_role** for every task. Only use target_model for utility/boilerplate tasks that don't need a specific agent.
5. **Set context_documents** on each task — specific paths under kb/ that the agent should read. For example:
   - Backend tasks should reference: ["architecture/ARCHITECTURE.md", "architecture/tech-stack.md"]
   - Frontend tasks should reference: ["architecture/ARCHITECTURE.md"]
   - Tester tasks should reference the output files of the tasks they test
6. **Every implementation task is TDD-enforced** (tdd_required: true, validation includes "all tests must pass").
7. **Priority**: 1 = highest priority. Lower numbers run first.
8. **Dependencies**: depends_on must reference task IDs from earlier phases.

## Model Selection for Non-Agent Tasks
- "haiku": boilerplate, config files, simple file creation
- "sonnet": business logic, moderate complexity
- "opus": cross-cutting concerns, system design

## Product Specification
If a PRODUCT SPECIFICATION section is provided, it is the primary source of WHAT to build.
Implement ALL features, respect technical decisions, create pages/routes, build data models,
wire integrations, translate user stories into tasks, ensure every requirement is covered.

## Project Context
Use the project context to avoid recreating existing code, reference specific files in task
prompts, build on existing patterns, and include "Read <file> first" instructions.

For each task, write the prompt field as a COMPLETE instruction that includes:
1. What to do
2. Which kb/ documents to read (set context_documents field)
3. Which existing files to read first
4. Which patterns/conventions to follow

Output valid JSON matching the schema exactly. No markdown, no explanation.
"""


def _build_prompt(
    answers: dict,
    project_context: str = "",
    product_spec_context: str = "",
) -> str:
    parts = [f"Project description: {answers['description']}"]
    parts.append(f"Features: {', '.join(answers['features'])}")

    if answers.get("has_auth"):
        parts.append(f"Authentication: {answers.get('auth_type', 'jwt')}")
    if answers.get("has_db"):
        parts.append(f"Database: {answers.get('db_type', 'postgres')}")
    if answers.get("has_api"):
        parts.append("Exposes an API: yes")
    if answers.get("extra"):
        parts.append(f"Additional requirements: {answers['extra']}")

    parts.append(f"Number of phases: {answers.get('num_phases', 3)}")

    if product_spec_context:
        parts.append(
            "\n--- PRODUCT SPECIFICATION (product guide — what to build) ---\n"
            + product_spec_context
            + "\n--- END PRODUCT SPECIFICATION ---\n"
            "You MUST implement all features, pages, data models, and requirements "
            "described in the product specification above."
        )

    if project_context:
        parts.append(
            "\n--- PROJECT CONTEXT (current state of the codebase) ---\n"
            + project_context
            + "\n--- END PROJECT CONTEXT ---"
        )

    parts.append(
        "\nDecompose into phases. Every task needs: id, description, prompt, "
        "priority (1=highest), agent_role, depends_on, context_documents.\n"
        "\nPhase 1 MUST be architecture (agent_role: 'architect'). "
        "Phase 2 MUST be PM task breakdown (agent_role: 'project_manager'). "
        "Implementation tasks use agent_role: 'backend', 'frontend', or 'tester' as appropriate.\n"
        "In each task prompt, reference specific kb/ documents the agent should read.\n"
        "Set context_documents to the list of kb/ paths the agent needs for that task.\n"
        "Every task prompt MUST instruct the agent to write tests first, then implement. "
        "The task validation MUST include 'all tests must pass' as a completion criterion."
    )

    return "\n".join(parts)


PHASE_LIST_SCHEMA = {
    "type": "object",
    "properties": {
        "phases": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "phase_number": {"type": "integer"},
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "validation": {"type": "string"},
                    "tasks": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string"},
                                "description": {"type": "string"},
                                "prompt": {"type": "string"},
                                "priority": {"type": "integer"},
                                "target_model": {
                                    "type": "string",
                                    "enum": ["haiku", "sonnet", "opus"],
                                },
                                "target_agent": {"type": "string"},
                                "agent_role": {
                                    "type": "string",
                                    "enum": [
                                        "architect",
                                        "project_manager",
                                        "backend",
                                        "frontend",
                                        "tester",
                                    ],
                                },
                                "depends_on": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                                "tdd_required": {"type": "boolean"},
                                "context_documents": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                            },
                            "required": [
                                "id",
                                "description",
                                "prompt",
                                "priority",
                            ],
                        },
                    },
                },
                "required": [
                    "phase_number",
                    "title",
                    "description",
                    "validation",
                    "tasks",
                ],
            },
        }
    },
    "required": ["phases"],
}


def decompose(
    answers: dict,
    project_root: Path,
    project_context: str = "",
    product_spec_context: str = "",
) -> list[Phase]:
    """Use claude CLI (opus) to decompose requirements into phases/tasks."""
    user_prompt = _build_prompt(answers, project_context, product_spec_context)

    # Combine system + user prompt into a single stdin message.
    schema_str = json.dumps(PHASE_LIST_SCHEMA, indent=2)
    full_prompt = (
        MULTI_AGENT_DECOMPOSITION_SYSTEM_PROMPT
        + "\n\nYou MUST output JSON matching this exact schema:\n"
        + schema_str
        + "\n\n---\n\n"
        + user_prompt
        + "\n\nRespond with ONLY the JSON object. No markdown fences, no explanation."
    )

    cmd = [
        "claude",
        "--print",
        "--model", "opus",
        "--output-format", "json",
        "--max-turns", "15",
        "-",  # read prompt from stdin
    ]

    result = subprocess.run(
        cmd,
        input=full_prompt,
        capture_output=True,
        text=True,
        cwd=str(project_root),
        timeout=600,
    )

    # claude --output-format json returns JSON in stdout even on errors
    if result.returncode != 0:
        # Try to extract the result from stdout (claude puts it there even on failure)
        try:
            outer = json.loads(result.stdout)
            if outer.get("is_error"):
                errors = outer.get("errors", [])
                raise RuntimeError(
                    f"claude CLI error: {'; '.join(errors) if errors else 'unknown error'}"
                )
        except (json.JSONDecodeError, TypeError):
            pass
        error_detail = result.stderr or result.stdout or "(no output)"
        raise RuntimeError(
            f"claude CLI failed (exit {result.returncode}):\n{error_detail[:1000]}"
        )

    # Parse output — claude --output-format json wraps in {"type":"result","result":...}
    try:
        outer = json.loads(result.stdout)
        # The result field contains the text response
        text = outer.get("result", result.stdout)
        if isinstance(text, str):
            # Try to extract JSON from the text
            # Look for the JSON object in the response
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                data = json.loads(text[start:end])
            else:
                data = json.loads(text)
        else:
            data = text
    except (json.JSONDecodeError, TypeError):
        # Try parsing stdout directly
        start = result.stdout.find("{")
        end = result.stdout.rfind("}") + 1
        if start >= 0 and end > start:
            data = json.loads(result.stdout[start:end])
        else:
            raise RuntimeError(
                f"Failed to parse claude output as JSON:\n{result.stdout[:500]}"
            )

    phases_data = data.get("phases", [data] if "phase_number" in data else [])
    phases = [Phase.model_validate(p) for p in phases_data]

    return phases
