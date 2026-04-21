import os
import re
import shutil
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table

app = typer.Typer(name="orai", help="Meta-Agentic Project Orchestrator")
agents_app = typer.Typer(name="agents", help="Manage project agents.", invoke_without_command=True)
app.add_typer(agents_app)
console = Console()


METATIEN_ROOT = Path(__file__).resolve().parent.parent.parent
METATIEN_BIN = METATIEN_ROOT / ".venv" / "bin" / "orai"


def _check_claude_installed() -> None:
    """Verify that the claude CLI is available in PATH."""
    if shutil.which("claude") is None:
        console.print(
            Panel(
                "[bold red]claude CLI not found in PATH[/bold red]\n\n"
                "orai depends on Claude Code CLI to execute tasks.\n"
                "Install it first: [bold]npm install -g @anthropic-ai/claude-code[/bold]\n\n"
                "Docs: https://docs.anthropic.com/en/docs/claude-code",
                title="Missing Dependency",
                border_style="red",
            )
        )
        raise typer.Exit(1)


def _detect_shell() -> tuple[str, Path]:
    """Detect user's default shell and return (shell_name, rc_file)."""
    shell = os.environ.get("SHELL", "/bin/bash")
    shell_name = Path(shell).name

    home = Path.home()
    rc_files = {
        "fish": home / ".config" / "fish" / "config.fish",
        "zsh": home / ".zshrc",
        "bash": home / ".bashrc",
    }

    rc_file = rc_files.get(shell_name, home / ".bashrc")
    return shell_name, rc_file


def _build_alias_line(shell_name: str) -> str:
    """Build the alias line for the detected shell."""
    if shell_name == "fish":
        return f'alias orai "{METATIEN_BIN}"'
    return f'alias orai="{METATIEN_BIN}"'


ALIAS_MARKER = "# orai-alias"


@app.command()
def install() -> None:
    """Add orai alias to your shell config so it works globally."""
    _check_claude_installed()
    if not METATIEN_BIN.exists():
        console.print(
            f"[red]orai binary not found at {METATIEN_BIN}.\n"
            "Run 'uv venv && uv pip install -e .' first.[/red]"
        )
        raise typer.Exit(1)

    shell_name, rc_file = _detect_shell()
    alias_line = _build_alias_line(shell_name)
    full_line = f"{alias_line}  {ALIAS_MARKER}\n"

    # Check if already installed
    if rc_file.exists():
        content = rc_file.read_text()
        if ALIAS_MARKER in content:
            console.print(f"[yellow]Alias already exists in {rc_file}[/yellow]")
            return

    # Append alias
    with rc_file.open("a") as f:
        f.write(f"\n{full_line}")

    console.print(
        f"[green]Added alias to {rc_file}[/green]\n"
        f"  {alias_line}\n\n"
        f"Run [bold]source {rc_file}[/bold] or restart your terminal to use it."
    )


@app.command()
def init(
    name: Optional[str] = typer.Argument(None, help="Project name (new) or path to existing project (with --existing)"),
    template: str = typer.Option("nextjs", "--template", "-t", help="nextjs | python | node | go"),
    path: Path = typer.Option(".", "--path", "-p", help="Parent directory"),
    existing: bool = typer.Option(False, "--existing", "-e", help="Initialize orai in an existing project directory"),
    ai_analyze: bool = typer.Option(False, "--ai", help="Use AI to analyze existing codebase and generate architecture doc"),
) -> None:
    """Scaffold a new project or initialize orai in an existing project."""
    _check_claude_installed()

    if existing:
        from orai.scaffold.existing import detect_project_info, scaffold_existing

        project_root = path.resolve() if name is None or name == "." else Path(name).resolve()
        if not project_root.exists():
            console.print(f"[red]Directory not found: {project_root}[/red]")
            raise typer.Exit(1)
        if not project_root.is_dir():
            console.print(f"[red]Not a directory: {project_root}[/red]")
            raise typer.Exit(1)

        console.print("[cyan]Detecting project info...[/cyan]")
        info = detect_project_info(project_root)

        console.print(
            f"[green]Detected:[/green] {info.name} ({info.project_type})\n"
            f"  Framework: {info.framework or '(none detected)'}\n"
            f"  Language:  {info.language_stack.value if info.language_stack else '(none detected)'}\n"
            f"  Has tests: {'yes' if info.has_tests else 'no'}\n"
            f"  Description: {info.description[:80] + '...' if len(info.description) > 80 else info.description}"
        )
        console.print()

        scaffold_existing(project_root, info, ai_analyze=ai_analyze)
        console.print(f"[green]orai initialized at {project_root}[/green]")
        console.print(f"[dim]Run 'orai plan {project_root}' to generate a task plan.[/dim]")
    else:
        from orai.scaffold.engine import scaffold

        if name is None:
            console.print("[red]Project name is required. Usage: orai init <name>[/red]")
            raise typer.Exit(1)

        project_root = scaffold(name, template, path)
        console.print(f"[green]Project created at {project_root}[/green]")


@app.command()
def plan(
    project: Path = typer.Argument(".", help="Project root"),
    interactive: bool = typer.Option(True, "--interactive/--auto"),
    spec: Optional[Path] = typer.Option(
        None, "--spec", "-s",
        help="Path to a product spec file (e.g. PRODUCT.md) to guide planning",
    ),
) -> None:
    """Interview user, generate phases and task JSONs.

    When --spec is provided, the product specification file is parsed to extract
    features, requirements, pages/routes, data models, and technical decisions.
    This guides the AI planner to generate tasks that implement the full product.
    """
    _check_claude_installed()
    import json as _json

    from orai.config import ANSWERS_FILE
    from orai.executor.state import StateManager
    from orai.planner.context import generate_and_save_context, generate_context
    from orai.planner.interview import interview
    from orai.planner.decompose import decompose

    project = project.resolve()
    state = StateManager(project)
    answers_path = state.agents_dir / ANSWERS_FILE

    # Parse product spec if provided
    product_spec_context = ""
    if spec is not None:
        spec = spec.resolve()
        if not spec.exists():
            console.print(f"[red]Spec file not found: {spec}[/red]")
            raise typer.Exit(1)

        from orai.planner.product_spec import build_spec_context, parse_product_spec

        parsed = parse_product_spec(spec)
        product_spec_context = build_spec_context(parsed)

        console.print(f"\n[bold cyan]Product spec loaded:[/bold cyan] {spec}")
        if parsed["title"]:
            title_first_line = parsed["title"].splitlines()[0]
            console.print(f"  [bold]Product:[/bold]      {title_first_line}")
        if parsed["features"]:
            console.print(f"  [bold]Features:[/bold]     {len(parsed['features'])} feature(s)")
        if parsed["tech_decisions"]:
            console.print(f"  [bold]Tech:[/bold]         {len(parsed['tech_decisions'])} decision(s)")
        if parsed["requirements"]:
            console.print(f"  [bold]Requirements:[/bold] {len(parsed['requirements'])} requirement(s)")
        if parsed["pages_routes"]:
            console.print(f"  [bold]Pages:[/bold]        {len(parsed['pages_routes'])} page(s)/route(s)")
        if parsed["data_models"]:
            console.print(f"  [bold]Models:[/bold]       {len(parsed['data_models'])} data model(s)")
        if parsed["integrations"]:
            console.print(f"  [bold]Integrations:[/bold] {len(parsed['integrations'])} integration(s)")
        console.print()

    # Check for saved answers
    if answers_path.exists():
        saved = _json.loads(answers_path.read_text())
        console.print("\n[bold cyan]Previous answers found:[/bold cyan]\n")
        console.print(f"  [bold]Description:[/bold] {saved.get('description', '')}")
        console.print(f"  [bold]Features:[/bold]    {', '.join(saved.get('features', []))}")
        if saved.get("has_auth"):
            console.print(f"  [bold]Auth:[/bold]        {saved.get('auth_type', 'jwt')}")
        if saved.get("has_db"):
            console.print(f"  [bold]Database:[/bold]    {saved.get('db_type', 'postgres')}")
        console.print(f"  [bold]API:[/bold]         {'yes' if saved.get('has_api') else 'no'}")
        console.print(f"  [bold]Phases:[/bold]      {saved.get('num_phases', 3)}")
        if saved.get("extra"):
            console.print(f"  [bold]Extra:[/bold]       {saved.get('extra')}")
        console.print()

        use_saved = Confirm.ask("Use these answers?", default=True)
        if use_saved:
            answers = saved
        else:
            answers = interview()
    elif interactive:
        answers = interview()
    else:
        console.print("[red]Auto mode not yet implemented.[/red]")
        raise typer.Exit(1)

    # Save answers for next time
    answers_path.parent.mkdir(parents=True, exist_ok=True)
    answers_path.write_text(_json.dumps(answers, indent=2))

    console.print("[cyan]Scanning project for context...[/cyan]")
    project_context = generate_context(project)
    ctx_path = generate_and_save_context(project)
    console.print(f"[green]Project context saved to {ctx_path}[/green]")

    console.print("[cyan]Decomposing requirements into phases...[/cyan]")
    phases = decompose(answers, project, project_context, product_spec_context)

    from orai.executor.state import StateManager

    state = StateManager(project)
    for phase in phases:
        state.save_phase(phase)

    # Update project meta
    meta = state.load_project_meta()
    meta.phases = [p.phase_number for p in phases]
    state.save_project_meta(meta)

    console.print(
        f"[green]Generated {len(phases)} phase(s) "
        f"with {sum(len(p.tasks) for p in phases)} total tasks.[/green]"
    )


@app.command()
def run(
    project: Path = typer.Argument(".", help="Project root"),
    phase: Optional[int] = typer.Option(None, "--phase", help="Run specific phase"),
    task_id: Optional[str] = typer.Option(None, "--task", help="Run single task"),
    resume: bool = typer.Option(False, "--resume", help="Resume from last state"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show commands only"),
    ignore_model: bool = typer.Option(False, "--ignore-model", help="Skip --model flag, use claude CLI default"),
) -> None:
    """Execute tasks by shelling out to claude CLI."""
    if not dry_run:
        _check_claude_installed()
    from orai.executor.runner import run_project

    project = project.resolve()
    run_project(
        project_root=project,
        phase_num=phase,
        task_id=task_id,
        resume=resume,
        dry_run=dry_run,
        ignore_model=ignore_model,
    )


@app.command()
def status(
    project: Path = typer.Argument(".", help="Project root"),
) -> None:
    """Show current progress across all phases."""
    from orai.executor.state import StateManager
    from orai.tui.progress import print_status

    project = project.resolve()
    state = StateManager(project)
    meta = state.load_project_meta()
    phases = [state.load_phase(n) for n in meta.phases]
    print_status(meta, phases)


@app.command()
def pause(
    project: Path = typer.Argument(".", help="Project root"),
) -> None:
    """Write a pause sentinel; runner stops after current task."""
    from orai.executor.state import StateManager

    project = project.resolve()
    state = StateManager(project)
    state.set_pause()
    console.print("[yellow]Pause requested. Runner will stop after current task.[/yellow]")


def _read_multiline(prompt_text: str) -> str:
    """Read multi-line input until user enters a blank line."""
    console.print(prompt_text)
    lines: list[str] = []
    while True:
        try:
            line = Prompt.ask("", default="")
        except (EOFError, KeyboardInterrupt):
            break
        if line == "":
            break
        lines.append(line)
    return "\n".join(lines)


def _slugify(name: str) -> str:
    """Convert agent name to email-friendly slug."""
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


@agents_app.callback()
def agents_list(
    ctx: typer.Context,
    project: Path = typer.Argument(".", help="Project root"),
) -> None:
    """List all configured agents. Run a subcommand (e.g. 'add') to manage them."""
    if ctx.invoked_subcommand is not None:
        return

    from orai.executor.state import StateManager

    project = project.resolve()
    state = StateManager(project)
    config = state.load_agents_config()

    if not config.agents:
        console.print(
            "[yellow]No agents configured.[/yellow]\n"
            "Run [bold]orai agents add <project>[/bold] to create one."
        )
        return

    meta = state.load_project_meta()
    console.print(f"\n[bold cyan]Agents — {meta.name}[/bold cyan]\n")

    table = Table(show_header=True, header_style="bold")
    table.add_column("Name")
    table.add_column("Role")
    table.add_column("Email")
    table.add_column("Skills")
    table.add_column("Scripts")
    table.add_column("Model")

    for agent in config.agents:
        role_label = agent.role.value if hasattr(agent, "role") else "backend"
        lang_label = ""
        if hasattr(agent, "language_stack") and agent.language_stack:
            lang_label = f" ({agent.language_stack.value})"
        table.add_row(
            agent.name,
            f"{role_label}{lang_label}",
            agent.email,
            ", ".join(agent.skills) if agent.skills else "[dim](none)[/dim]",
            ", ".join(agent.scripts) if agent.scripts else "[dim](none)[/dim]",
            agent.model.value,
        )

    console.print(table)
    console.print(f"\n[dim]{len(config.agents)} agent(s) configured.[/dim]")


@agents_app.command("add")
def agents_add(
    project: Path = typer.Argument(".", help="Project root"),
) -> None:
    """Interactively add a new agent to the project."""
    from orai.executor.state import StateManager
    from orai.models import AgentProfile, AgentRole, LanguageStack, TargetModel

    project = project.resolve()
    state = StateManager(project)
    config = state.load_agents_config()

    console.print("\n[bold cyan]Add New Agent[/bold cyan] [dim](7 fields)[/dim]\n")

    # 1. Name
    name = Prompt.ask("[bold][1/7] Agent name[/bold]")
    if not name.strip():
        console.print("[red]Name is required.[/red]")
        raise typer.Exit(1)
    name = name.strip()

    # Check duplicate
    existing_names = {a.name for a in config.agents}
    if name in existing_names:
        console.print(f"[red]Agent '{name}' already exists.[/red]")
        raise typer.Exit(1)

    # 2. Email
    default_email = f"{_slugify(name)}@project.local"
    email = Prompt.ask("[bold][2/7] Email[/bold]", default=default_email)

    # 3. Role
    role_str = Prompt.ask(
        "[bold][3/7] Role[/bold]",
        choices=["architect", "project_manager", "backend", "frontend", "tester"],
        default="backend",
    )
    role = AgentRole(role_str)

    # 4. Language stack (only for backend)
    language_stack = None
    if role == AgentRole.BACKEND:
        lang_str = Prompt.ask(
            "[bold][4/7] Language stack[/bold]",
            choices=["python", "node", "go"],
            default="python",
        )
        language_stack = LanguageStack(lang_str)

    field_num = "5/7" if language_stack is not None else "4/7"
    # 5. Skills
    skills_raw = Prompt.ask(
        f"[bold][{field_num}] Skills[/bold] [dim](comma-separated, match ## sections in Skills.md)[/dim]",
        default="",
    )
    skills = [s.strip() for s in skills_raw.split(",") if s.strip()]

    # 6. Scripts
    field_num = "6/7" if language_stack is not None else "5/7"
    scripts_raw = Prompt.ask(
        f"[bold][{field_num}] Scripts[/bold] [dim](comma-separated, optional — match ### entries in Skills.md)[/dim]",
        default="",
    )
    scripts = [s.strip() for s in scripts_raw.split(",") if s.strip()]

    # 7. Model
    field_num = "7/7" if language_stack is not None else "6/7"
    model_str = Prompt.ask(
        f"[bold][{field_num}] Model[/bold]",
        choices=["haiku", "sonnet", "opus"],
        default="sonnet",
    )
    model = TargetModel(model_str)

    # Summary
    lang_display = f" ({language_stack.value})" if language_stack else ""
    summary = (
        f"[bold]Name:[/bold]    {name}\n"
        f"[bold]Role:[/bold]    {role.value}{lang_display}\n"
        f"[bold]Email:[/bold]   {email}\n"
        f"[bold]Skills:[/bold]  {', '.join(skills) if skills else '(none)'}\n"
        f"[bold]Scripts:[/bold] {', '.join(scripts) if scripts else '(none)'}\n"
        f"[bold]Model:[/bold]   {model.value}"
    )
    console.print()
    console.print(Panel(summary, title="New Agent", border_style="green"))

    if not Confirm.ask("\nAdd this agent?", default=True):
        console.print("[yellow]Cancelled.[/yellow]")
        raise typer.Exit(0)

    # Save agent
    agent = AgentProfile(
        name=name,
        email=email,
        role=role,
        language_stack=language_stack,
        skills=skills,
        scripts=scripts,
        model=model,
        system_prompt_template=f"backend-{language_stack.value}" if language_stack else role.value,
    )
    config.agents.append(agent)
    state.save_agents_config(config)
    console.print(f"\n[green]Agent '{name}' added.[/green]")

    # Offer to add missing skill sections to Skills.md
    for skill in skills:
        if state.skill_section_exists(skill):
            continue
        console.print(
            f"\n[yellow]Skill '{skill}' not found in Skills.md.[/yellow]"
        )
        if Confirm.ask(f"Add a [bold]## {skill}[/bold] section now?", default=True):
            console.print(
                f"\n[dim]Skills.md is a Markdown (.md) file.[/dim]\n"
                f"[dim]Type or paste content for the \"{skill}\" skill section below.[/dim]\n"
                f"[dim]Enter a blank line to finish.[/dim]\n"
            )
            content = _read_multiline("")
            if content.strip():
                state.append_skill_section(skill, content)
                console.print(f"[green]Added ## {skill} section to Skills.md.[/green]")
            else:
                state.append_skill_section(skill, f"Skills for {skill}.\n")
                console.print(f"[green]Added ## {skill} section (placeholder) to Skills.md.[/green]")

    skills_path = state.app_dir / ".agents" / "Skills.md"
    console.print(f"\n[dim]You can edit Skills.md anytime at {skills_path}[/dim]")


@app.command()
def reset(
    project: Path = typer.Argument(".", help="Project root"),
    task_id: Optional[str] = typer.Option(None, "--task", help="Reset specific task"),
    phase: Optional[int] = typer.Option(None, "--phase", help="Reset entire phase"),
) -> None:
    """Reset task(s) back to pending."""
    from orai.executor.state import StateManager
    from orai.models import TaskStatus

    project = project.resolve()
    state = StateManager(project)

    if phase is not None:
        p = state.load_phase(phase)
        for t in p.tasks:
            t.status = TaskStatus.PENDING
            t.started_at = None
            t.completed_at = None
            t.error = None
            t.output_summary = None
        state.save_phase(p)
        console.print(f"[green]Reset all tasks in phase {phase}.[/green]")
    elif task_id is not None:
        phase_num = int(task_id.split(".")[0])
        p = state.load_phase(phase_num)
        for t in p.tasks:
            if t.id == task_id:
                t.status = TaskStatus.PENDING
                t.started_at = None
                t.completed_at = None
                t.error = None
                t.output_summary = None
                break
        else:
            console.print(f"[red]Task {task_id} not found.[/red]")
            raise typer.Exit(1)
        state.save_phase(p)
        console.print(f"[green]Reset task {task_id}.[/green]")
    else:
        console.print("[red]Specify --task or --phase.[/red]")
        raise typer.Exit(1)


@app.command()
def context(
    project: Path = typer.Argument(".", help="Project root"),
) -> None:
    """Generate .agents/plan_state.json with project status and TDD guidelines."""
    from orai.executor.state import StateManager
    from orai.planner.plan_state import generate_plan_state

    state = StateManager(project)
    plan_state = generate_plan_state(project)

    state.save_plan_state(plan_state)

    output_path = state.agents_dir / "plan_state.json"
    console.print(f"[green]Plan state saved to {output_path}[/green]")
    console.print(f"[dim]Project: {plan_state.project_name} | Status: {plan_state.overall_status}[/dim]")
    if plan_state.next_actionable_tasks:
        console.print(f"[bold]Next tasks:[/bold]")
        for nt in plan_state.next_actionable_tasks:
            console.print(f"  {nt['id']}: {nt['description']}")


@app.command()
def ui(
    project: Path = typer.Argument(".", help="Project root"),
    port: int = typer.Option(8888, "--port", "-p", help="Port to serve on"),
) -> None:
    """Launch the web UI to monitor project progress."""
    from orai.web.server import start_ui

    project = project.resolve()
    console.print(f"[cyan]Starting orai UI on http://127.0.0.1:{port}[/cyan]")
    console.print(f"[dim]Project: {project}[/dim]\n")
    start_ui(project, port=port)


@app.command()
def report(
    project: Path = typer.Argument(".", help="Project root"),
) -> None:
    """Show project plan, progress, problems, and document graph status."""
    from orai.config import KB_INDEX_FILE, ORCHESTRATION_CONFIG_FILE
    from orai.executor.state import StateManager
    from orai.models import TaskStatus

    project = project.resolve()
    state = StateManager(project)
    meta = state.load_project_meta()
    phases = [state.load_phase(n) for n in meta.phases]

    # --- Project Overview ---
    console.print(Panel(
        f"[bold]{meta.name}[/bold] ({meta.project_type})\n"
        f"Created: {meta.created_at.strftime('%Y-%m-%d %H:%M UTC')}\n"
        f"Current phase: {meta.current_phase}",
        title="Project Overview",
        border_style="cyan",
    ))

    # --- Overall Progress ---
    total = sum(len(p.tasks) for p in phases)
    done = sum(1 for p in phases for t in p.tasks if t.status == TaskStatus.DONE)
    failed = sum(1 for p in phases for t in p.tasks if t.status == TaskStatus.FAILED)
    running = sum(1 for p in phases for t in p.tasks if t.status == TaskStatus.RUNNING)
    pending = sum(1 for p in phases for t in p.tasks if t.status == TaskStatus.PENDING)

    progress_pct = (done / total * 100) if total > 0 else 0

    console.print(f"\n[bold]Progress: {progress_pct:.0f}%[/bold] "
                  f"({done}/{total} done, {failed} failed, {running} running, {pending} pending)")

    # --- Problems Panel ---
    problems = []
    for phase in phases:
        for task in phase.tasks:
            if task.status == TaskStatus.FAILED:
                error_preview = (task.error or "unknown error")[:100]
                problems.append(f"[red]FAIL {task.id}[/red] ({phase.title}): {error_preview}")

    if problems:
        console.print(Panel("\n".join(problems), title=f"Problems ({len(problems)})", border_style="red"))
    else:
        console.print("[green]No problems detected.[/green]")

    # --- Phase Summary ---
    table = Table(show_header=True, header_style="bold")
    table.add_column("Phase")
    table.add_column("Title")
    table.add_column("Done")
    table.add_column("Failed")
    table.add_column("Pending")
    table.add_column("Next Task")

    for phase in phases:
        done_c = sum(1 for t in phase.tasks if t.status == TaskStatus.DONE)
        fail_c = sum(1 for t in phase.tasks if t.status == TaskStatus.FAILED)
        pend_c = sum(1 for t in phase.tasks if t.status == TaskStatus.PENDING)
        next_task = None
        for t in sorted(phase.tasks, key=lambda t: t.priority):
            if t.status == TaskStatus.PENDING and all(
                d in {t2.id for t2 in phase.tasks if t2.status == TaskStatus.DONE}
                for d in t.depends_on
            ):
                next_task = f"{t.id}: {t.description[:40]}"
                break
        table.add_row(
            str(phase.phase_number),
            phase.title,
            str(done_c),
            str(fail_c) if fail_c else "",
            str(pend_c),
            next_task or "[dim](none)[/dim]",
        )

    console.print("\n", table, sep="")

    # --- Document Graph Status ---
    kb_index_path = state.agents_dir / KB_INDEX_FILE
    if kb_index_path.exists():
        import json as _json
        index = _json.loads(kb_index_path.read_text())
        if index:
            console.print(f"\n[bold]Document Graph:[/bold] {len(index)} document(s)")
            doc_table = Table(show_header=True, header_style="bold")
            doc_table.add_column("Path")
            doc_table.add_column("Title")
            doc_table.add_column("Produced By")
            for doc in index:
                doc_table.add_row(
                    doc.get("path", ""),
                    doc.get("title", ""),
                    doc.get("produced_by_task", "") or "[dim](manual)[/dim]",
                )
            console.print(doc_table)
        else:
            console.print("\n[dim]Document Graph: no documents yet[/dim]")
    else:
        console.print("\n[dim]Document Graph: not initialized[/dim]")
