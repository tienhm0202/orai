from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from orai.config import (
    CONTEXT_DOC_FILE,
    KB_DIR,
    KB_INDEX_FILE,
    PROJECT_META_FILE,
    AGENTS_CONFIG_FILE,
    ORCHESTRATION_CONFIG_FILE,
    SKILLS_DOC_FILE,
    TEMPLATES_DIR,
)
from orai.models import AgentProfile, AgentRole, AgentsConfig, LanguageStack, OrchestrationConfig, ProjectMeta


@dataclass
class ProjectInfo:
    name: str
    project_type: str
    language_stack: LanguageStack | None
    framework: str
    description: str
    has_tests: bool


def _detect_tech_stack_from_files(root: Path) -> dict:
    """Detect technology stack from config files, reused from planner/context.py logic."""
    stack: dict = {}

    pkg_json = root / "package.json"
    if pkg_json.exists():
        try:
            data = json.loads(pkg_json.read_text())
            deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
            stack["runtime"] = "Node.js"
            if "next" in deps:
                stack["framework"] = f"Next.js {deps['next']}"
            elif "react" in deps:
                stack["framework"] = f"React {deps['react']}"
            elif "vue" in deps:
                stack["framework"] = f"Vue {deps['vue']}"
            elif "express" in deps or "hono" in deps:
                stack["framework"] = "Express/Hono"
            if "tailwindcss" in deps:
                stack["css"] = "Tailwind CSS"
            if "typescript" in deps:
                stack["language"] = "TypeScript"
        except (json.JSONDecodeError, OSError):
            pass

    pyproject = root / "pyproject.toml"
    if pyproject.exists():
        try:
            content = pyproject.read_text()
            stack["runtime"] = "Python"
            if "fastapi" in content.lower():
                stack["framework"] = "FastAPI"
            elif "django" in content.lower():
                stack["framework"] = "Django"
            elif "flask" in content.lower():
                stack["framework"] = "Flask"
            if "sqlalchemy" in content.lower():
                stack["orm"] = "SQLAlchemy"
            if "alembic" in content.lower():
                stack["migrations"] = "Alembic"
        except OSError:
            pass

    go_mod = root / "go.mod"
    if go_mod.exists():
        stack["runtime"] = "Go"
        try:
            first_line = go_mod.read_text().splitlines()[0]
            if first_line.startswith("module "):
                stack["module"] = first_line.split(" ", 1)[1]
        except OSError:
            pass

    return stack


def _detect_project_name(root: Path) -> str:
    """Infer project name from config files or directory name."""
    # package.json "name"
    pkg_json = root / "package.json"
    if pkg_json.exists():
        try:
            data = json.loads(pkg_json.read_text())
            if data.get("name"):
                return data["name"]
        except (json.JSONDecodeError, OSError):
            pass

    # pyproject.toml [project].name
    pyproject = root / "pyproject.toml"
    if pyproject.exists():
        try:
            content = pyproject.read_text()
            for line in content.splitlines():
                if line.startswith("name = "):
                    return line.split("=", 1)[1].strip().strip("\"'")
        except OSError:
            pass

    # go.mod module path
    go_mod = root / "go.mod"
    if go_mod.exists():
        try:
            for line in go_mod.read_text().splitlines():
                if line.startswith("module "):
                    module = line.split(" ", 1)[1]
                    return module.split("/")[-1]
        except OSError:
            pass

    # CLAUDE.md first heading
    claude_md = root / "CLAUDE.md"
    if claude_md.exists():
        try:
            for line in claude_md.read_text().splitlines():
                if line.startswith("# "):
                    return line[2:].strip()
        except OSError:
            pass

    # Fall back to directory name
    return root.name


def _detect_project_type(stack: dict) -> str:
    """Map detected tech stack to orai project type."""
    framework = stack.get("framework", "").lower()
    runtime = stack.get("runtime", "").lower()

    if "next.js" in framework:
        return "nextjs"
    if "react" in framework or "vue" in framework:
        return "nextjs"  # closest template for frontend
    if runtime == "python":
        return "python"
    if runtime == "go":
        return "go"
    if runtime == "node.js":
        return "node"

    return "python"  # default fallback


def _detect_language_stack(stack: dict) -> LanguageStack | None:
    runtime = stack.get("runtime", "").lower()
    mapping = {
        "python": LanguageStack.PYTHON,
        "node.js": LanguageStack.NODE,
        "go": LanguageStack.GO,
    }
    return mapping.get(runtime)


def _detect_has_tests(root: Path) -> bool:
    """Check if the project has test files or test framework configured."""
    test_indicators = [
        # File patterns
        bool(list(root.glob("test_*.py"))),
        bool(list(root.glob("*_test.py"))),
        bool(list(root.glob("**/*.test.ts"))),
        bool(list(root.glob("**/*.test.tsx"))),
        bool(list(root.glob("**/*.test.js"))),
        bool(list(root.glob("**/*_test.go"))),
        # Directories
        (root / "tests").exists(),
        (root / "test").exists(),
        # Config indicators
        "pytest" in (root / "pyproject.toml").read_text().lower() if (root / "pyproject.toml").exists() else False,
        "jest" in (root / "package.json").read_text().lower() if (root / "package.json").exists() else False,
    ]
    return any(test_indicators)


def _read_description(root: Path) -> str:
    """Extract a short description from README.md or CLAUDE.md."""
    for filename in ("README.md", "README", "CLAUDE.md"):
        path = root / filename
        if path.exists():
            try:
                content = path.read_text()
                # Skip heading lines
                lines = content.splitlines()
                text_lines = [l for l in lines if not l.startswith("# ") and l.strip()]
                # Take first non-empty paragraph (up to 200 chars)
                desc = " ".join(text_lines[:3])
                return desc[:200].strip()
            except OSError:
                pass
    return ""


def detect_project_info(project_root: Path) -> ProjectInfo:
    """Scan an existing project and infer its metadata."""
    stack = _detect_tech_stack_from_files(project_root)
    name = _detect_project_name(project_root)
    project_type = _detect_project_type(stack)
    language_stack = _detect_language_stack(stack)
    framework = stack.get("framework", "")
    has_tests = _detect_has_tests(project_root)
    description = _read_description(project_root)

    return ProjectInfo(
        name=name,
        project_type=project_type,
        language_stack=language_stack,
        framework=framework,
        description=description,
        has_tests=has_tests,
    )


def _is_frontend_capable(project_type: str, framework: str) -> bool:
    """Check if the detected stack includes a frontend framework."""
    if project_type == "nextjs":
        return True
    fw = framework.lower()
    return "react" in fw or "vue" in fw or "angular" in fw or "next.js" in fw


def generate_default_agents(info: ProjectInfo) -> AgentsConfig:
    """Generate a default agent config based on detected project info."""
    agents: list[AgentProfile] = []

    # Architect — always included
    agents.append(AgentProfile(
        name="Solution Architect",
        email=f"architect@{info.name.lower().replace(' ', '-')}.local",
        role=AgentRole.ARCHITECT,
        skills=["architecture-design", "tech-stack-selection"],
        scripts=[],
        model="opus",
        system_prompt_template="architect",
    ))

    # PM — always included
    agents.append(AgentProfile(
        name="Project Manager",
        email=f"pm@{info.name.lower().replace(' ', '-')}.local",
        role=AgentRole.PROJECT_MANAGER,
        skills=["task-breakdown", "tdd-enforcement"],
        scripts=[],
        model="opus",
        system_prompt_template="pm",
    ))

    # Backend — included if we detected a language stack
    if info.language_stack:
        agents.append(AgentProfile(
            name="Backend Developer",
            email=f"backend@{info.name.lower().replace(' ', '-')}.local",
            role=AgentRole.BACKEND,
            language_stack=info.language_stack,
            skills=["backend-api", "testing"],
            scripts=[],
            model="sonnet",
            system_prompt_template=f"backend-{info.language_stack.value}",
        ))

    # Frontend — included if frontend-capable
    if _is_frontend_capable(info.project_type, info.framework):
        agents.append(AgentProfile(
            name="Frontend Developer",
            email=f"frontend@{info.name.lower().replace(' ', '-')}.local",
            role=AgentRole.FRONTEND,
            skills=["frontend"],
            scripts=[],
            model="sonnet",
            system_prompt_template="frontend",
        ))

    # Tester — always included
    agents.append(AgentProfile(
        name="Tester",
        email=f"tester@{info.name.lower().replace(' ', '-')}.local",
        role=AgentRole.TESTER,
        skills=["testing", "bug-reporting"],
        scripts=[],
        model="sonnet",
        system_prompt_template="tester",
    ))

    return AgentsConfig(agents=agents)


def generate_skills_scaffold(info: ProjectInfo) -> str:
    """Generate a Skills.md based on the closest template for detected project type."""
    template_dir = TEMPLATES_DIR / info.project_type
    if not template_dir.exists():
        template_dir = TEMPLATES_DIR / "python"  # fallback

    skills_template = template_dir / "Skills.md.j2"
    if skills_template.exists():
        env = Environment(loader=FileSystemLoader(str(template_dir)), keep_trailing_newline=True)
        tmpl = env.get_template("Skills.md.j2")
        return tmpl.render(project_name=info.name, project_type=info.project_type)

    # Absolute fallback — minimal generic Skills.md
    return f"# Agent Skills Reference — {info.name}\n\n" \
           f"Agents invoke scripts via the Bash tool using paths relative to the project root.\n" \
           f"Scripts live in `.agents/scripts/`.\n\n" \
           f"---\n\n" \
           f"## backend\n\n" \
           f"Skills for implementing backend logic.\n\n" \
           f"---\n\n" \
           f"## testing\n\n" \
           f"Skills for writing and running tests.\n"


def scaffold_existing(
    project_root: Path,
    info: ProjectInfo,
    ai_analyze: bool = False,
) -> Path:
    """Initialize orai management structure in an existing project.

    Does NOT create template app files — only .agents/ directory, config,
    knowledge base structure, and context documents.

    Returns the project root path.
    """
    agents_dir = project_root
    existing_agents = agents_dir / ".agents"

    if existing_agents.exists():
        from rich.console import Console
        from rich.prompt import Confirm
        console = Console()
        console.print(
            f"[yellow]Warning: {existing_agents} already exists.[/yellow]"
        )
        if not Confirm.ask("Continue? This may overwrite existing orai config.", default=False):
            raise RuntimeError("Aborted: .agents/ already exists.")

    # Create directory structure
    dirs_to_create = [
        ".agents/tasks",
        ".agents/scripts",
        f"{KB_DIR}/architecture/decisions",
        f"{KB_DIR}/phases",
        f"{KB_DIR}/agent-contexts",
        f"{KB_DIR}/shared",
        f"{KB_DIR}/task-outputs",
    ]
    for d in dirs_to_create:
        (agents_dir / d).mkdir(parents=True, exist_ok=True)

    # Write project.json
    meta = ProjectMeta(
        name=info.name,
        project_type=info.project_type,
        created_at=datetime.now(timezone.utc),
    )
    (agents_dir / PROJECT_META_FILE).write_text(meta.model_dump_json(indent=2))

    # Write agents.json
    agents_config = generate_default_agents(info)
    (agents_dir / AGENTS_CONFIG_FILE).write_text(agents_config.model_dump_json(indent=2))

    # Write orchestration.json
    orchestration = OrchestrationConfig(
        language_stack=info.language_stack or LanguageStack.PYTHON,
        architecture_decisions=[],
        architect_first=True,
        pm_enforces_tdd=True,
        tester_enabled=True,
        max_retry_loops=3,
    )
    (agents_dir / ORCHESTRATION_CONFIG_FILE).write_text(orchestration.model_dump_json(indent=2))

    # Write kb/_index.json
    (agents_dir / KB_INDEX_FILE).write_text("[]")

    # Write kb/shared/tdd-guidelines.md from template
    template_dir = TEMPLATES_DIR / info.project_type
    if not template_dir.exists():
        template_dir = TEMPLATES_DIR / "python"
    tdd_template = template_dir / "tdd-guidelines.md.j2"
    if tdd_template.exists():
        env = Environment(loader=FileSystemLoader(str(template_dir)), keep_trailing_newline=True)
        tmpl = env.get_template("tdd-guidelines.md.j2")
        (agents_dir / KB_DIR / "shared" / "tdd-guidelines.md").write_text(
            tmpl.render(project_name=info.name, project_type=info.project_type)
        )
    else:
        (agents_dir / KB_DIR / "shared" / "tdd-guidelines.md").write_text(
            "# TDD Guidelines\n\nWrite tests before implementing code.\n"
        )

    # Write Skills.md
    (agents_dir / SKILLS_DOC_FILE).write_text(generate_skills_scaffold(info))

    # Generate CONTEXT.md by scanning project
    from orai.planner.context import generate_context
    context_content = generate_context(project_root)
    context_path = agents_dir / CONTEXT_DOC_FILE
    context_path.write_text(context_content, encoding="utf-8")

    # Optional AI analysis
    if ai_analyze:
        _run_ai_analysis(project_root, agents_dir, info)

    return project_root


def _run_ai_analysis(project_root: Path, agents_dir: Path, info: ProjectInfo) -> None:
    """Use claude CLI to analyze the project and produce an architecture summary."""
    from rich.console import Console
    console = Console()
    console.print("[cyan]Running AI analysis of project...[/cyan]")

    prompt = (
        f"Analyze this project and produce a concise ARCHITECTURE.md document.\n\n"
        f"Project: {info.name}\n"
        f"Type: {info.project_type}\n"
        f"Framework: {info.framework}\n\n"
        f"Scan the codebase, README, config files, and documentation.\n"
        f"Produce a markdown document with:\n"
        f"- System overview\n"
        f"- Directory structure summary\n"
        f"- Key architectural patterns and decisions\n"
        f"- Main components and their relationships\n"
        f"- Tech stack summary\n\n"
        f"Output ONLY the markdown content, no explanations."
    )

    try:
        result = subprocess.run(
            ["claude", "--print", "--model", "sonnet", "--max-turns", "10", "-p", prompt],
            capture_output=True,
            text=True,
            cwd=str(project_root),
            timeout=300,
        )

        if result.returncode == 0:
            arch_content = result.stdout.strip()
            if arch_content:
                # Clean up markdown code fences if claude wrapped them
                if arch_content.startswith("```markdown"):
                    arch_content = arch_content.removeprefix("```markdown").removesuffix("```").strip()
                elif arch_content.startswith("```"):
                    arch_content = arch_content.removeprefix("```").removesuffix("```").strip()

                arch_path = agents_dir / KB_DIR / "architecture" / "ARCHITECTURE.md"
                arch_path.write_text(arch_content, encoding="utf-8")

                # Register in KB index
                index_path = agents_dir / KB_INDEX_FILE
                index = json.loads(index_path.read_text())
                index.append({
                    "path": "architecture/ARCHITECTURE.md",
                    "title": "Architecture Overview",
                    "description": f"AI-generated architecture analysis of {info.name}",
                    "produced_by_task": "init-existing-ai",
                    "consumed_by_roles": ["architect", "backend", "frontend", "tester"],
                })
                index_path.write_text(json.dumps(index, indent=2))

                console.print(f"[green]Architecture analysis saved to {arch_path}[/green]")
            else:
                console.print("[yellow]AI analysis returned empty content.[/yellow]")
        else:
            error = result.stderr[:300] if result.stderr else result.stdout[:300]
            console.print(f"[yellow]AI analysis failed: {error}[/yellow]")
    except subprocess.TimeoutExpired:
        console.print("[yellow]AI analysis timed out (5 min limit).[/yellow]")
    except FileNotFoundError:
        console.print("[yellow]claude CLI not found. Skipping AI analysis.[/yellow]")
