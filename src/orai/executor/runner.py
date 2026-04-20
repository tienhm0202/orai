from __future__ import annotations

import re
import signal
import subprocess
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from rich.console import Console

from orai.config import DEFAULT_TASK_TIMEOUT, MODEL_FLAGS, PROMPTS_DIR
from orai.executor.signals import ShutdownManager
from orai.executor.skills import extract_skill_sections, filter_scripts_section
from orai.executor.state import StateManager
from orai.models import AgentProfile, AgentRole, Phase, Task, TaskStatus
from orai.tui.progress import ProgressDisplay

console = Console()


def build_agent_system_prompt(
    agent: AgentProfile, skills_doc: str, context_doc: str = ""
) -> str:
    """Build the system prompt injected when running an agent-targeted task."""
    identity = (
        f"You are {agent.name} <{agent.email}>.\n"
        f"Your role: {', '.join(agent.skills) if agent.skills else 'general developer'}.\n\n"
        "When committing changes, use your name and email as the git author."
    )

    # Project context block — gives agent understanding of the codebase
    context_block = ""
    if context_doc:
        context_block = (
            "## Project Context\n\n"
            "Read this section to understand the project BEFORE exploring code.\n"
            "It describes the tech stack, directory structure, key files, and entry points.\n"
            "Use this to navigate efficiently — read only the files relevant to your task.\n\n"
            + context_doc
        )

    relevant = extract_skill_sections(skills_doc, agent.skills)
    if relevant and agent.scripts:
        h2_pattern = re.compile(r"(?m)^## .+$")
        matches = list(h2_pattern.finditer(relevant))
        filtered_parts = []
        for i, match in enumerate(matches):
            start = match.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(relevant)
            filtered_parts.append(
                filter_scripts_section(relevant[start:end], agent.scripts)
            )
        relevant = "\n\n".join(filtered_parts)

    skills_block = ""
    if relevant:
        skills_block = (
            "## Available Skills and Scripts\n\n"
            "Use the Bash tool to invoke scripts documented below.\n"
            "Scripts are located at `.agents/scripts/` relative to the project root.\n\n"
            + relevant
        )

    return "\n\n".join(part for part in [identity, context_block, skills_block] if part)


def _load_prompt_template(agent: AgentProfile) -> str:
    """Load the role-specific system prompt template from prompts/ directory."""
    template_name = agent.system_prompt_template or agent.role.value
    candidates = [
        PROMPTS_DIR / f"{template_name}.md.j2",
        PROMPTS_DIR / f"{agent.role.value}.md.j2",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate.read_text()
    return ""


def _render_prompt_template(template: str, agent: AgentProfile, task: Task, state: StateManager) -> str:
    """Simple template renderer — replaces {{ var }} with actual values."""
    if not template:
        return ""

    replacements = {
        "{{ agent.name }}": agent.name,
        "{{ agent.email }}": agent.email,
        "{{ agent.role }}": agent.role.value,
        "{{ project_rules }}": "",
        "{{ skills_block }}": "",
        "{{ project_type }}": "",
        "{{ language_stack }}": agent.language_stack.value if agent.language_stack else "unspecified",
        "{{ project_name }}": "",
        "{{ tech_stack_context }}": "",
        "{{ task_id }}": task.id,
    }

    try:
        meta = state.load_project_meta()
        replacements["{{ project_name }}"] = meta.name
        replacements["{{ project_type }}"] = meta.project_type
    except (FileNotFoundError, Exception):
        pass

    result = template
    for placeholder, value in replacements.items():
        result = result.replace(placeholder, value)

    return result


def build_agent_system_prompt_v2(
    agent: AgentProfile,
    task: Task,
    project_root: Path,
    skills_doc: str = "",
) -> str:
    """Build system prompt using document graph for targeted context.

    Uses role-specific prompt templates from prompts/ and only loads
    the KB documents relevant to this task, minimizing token usage.
    """
    state = StateManager(project_root)
    parts: list[str] = []

    # 1. Render role-specific prompt template
    template = _load_prompt_template(agent)
    rendered = _render_prompt_template(template, agent, task, state)
    if rendered:
        parts.append(rendered)
    else:
        # Fallback to identity-based prompt
        identity = (
            f"You are {agent.name} <{agent.email}>.\n"
            f"Your role: {', '.join(agent.skills) if agent.skills else agent.role.value}.\n\n"
            "When committing changes, use your name and email as the git author."
        )
        parts.append(identity)

    # 2. Load task-specific context documents from KB
    if task.context_documents:
        context_parts = []
        for doc_path in task.context_documents:
            content = state.read_kb_doc(doc_path)
            if content:
                context_parts.append(f"## Reference: {doc_path}\n\n{content}")
        if context_parts:
            parts.append("## Task Context Documents\n\n" + "\n\n".join(context_parts))

    # 3. Include architecture doc for non-architect agents (first 3000 chars)
    if agent.role != AgentRole.ARCHITECT:
        arch_content = state.read_kb_doc("architecture/ARCHITECTURE.md")
        if arch_content:
            parts.append("## Architecture\n\n" + arch_content[:3000])

    # 4. Append filtered skills
    if skills_doc and agent.skills:
        relevant = extract_skill_sections(skills_doc, agent.skills)
        if relevant and agent.scripts:
            h2_pattern = re.compile(r"(?m)^## .+$")
            matches = list(h2_pattern.finditer(relevant))
            filtered_parts = []
            for i, match in enumerate(matches):
                start = match.start()
                end = matches[i + 1].start() if i + 1 < len(matches) else len(relevant)
                filtered_parts.append(
                    filter_scripts_section(relevant[start:end], agent.scripts)
                )
            relevant = "\n\n".join(filtered_parts)
        if relevant:
            parts.append(
                "## Available Skills and Scripts\n\n"
                "Use the Bash tool to invoke scripts documented below.\n"
                "Scripts are located at `.agents/scripts/` relative to the project root.\n\n"
                + relevant
            )

    return "\n\n".join(parts)


def build_claude_command(
    task: Task,
    project_root: Path,
    system_prompt: Optional[str] = None,
    model_override: Optional[str] = None,
    ignore_model: bool = False,
) -> list[str]:
    """Build the argv list for a single task execution."""
    cmd = [
        "claude",
        "--print",
        "--max-turns", "50",
        "--permission-mode", "auto",
        "--allowedTools", ",".join(task.allowed_tools),
    ]
    if not ignore_model:
        model = model_override or MODEL_FLAGS[task.target_model.value]
        cmd += ["--model", model]
    if system_prompt:
        cmd += ["--system-prompt", system_prompt]
    cmd.append(task.prompt)
    return cmd


def execute_task(
    task: Task, project_root: Path, dry_run: bool = False, ignore_model: bool = False
) -> tuple[TaskStatus, Optional[str]]:
    """Run one task via claude CLI. Returns (new_status, output_or_error)."""
    system_prompt: Optional[str] = None
    model_flag: Optional[str] = None

    state = StateManager(project_root)
    context_doc = state.load_context_doc()
    skills_doc = state.load_skills_doc()

    if task.target_agent is not None:
        agent = state.resolve_agent(task.target_agent)
        if agent is None:
            return (
                TaskStatus.FAILED,
                f"Agent '{task.target_agent}' not found in agents.json",
            )
        system_prompt = build_agent_system_prompt(agent, skills_doc, context_doc)
        model_flag = MODEL_FLAGS[agent.model.value]
    elif task.agent_role is not None:
        agent = state.resolve_agent_by_role(task.agent_role)
        if agent is None:
            return (
                TaskStatus.FAILED,
                f"Agent with role '{task.agent_role.value}' not found in agents.json",
            )
        system_prompt = build_agent_system_prompt_v2(agent, task, project_root, skills_doc)
        model_flag = MODEL_FLAGS[agent.model.value]
    elif task.target_model is not None:
        model_flag = MODEL_FLAGS[task.target_model.value]
        # Non-agent tasks get project context
        if context_doc:
            system_prompt = (
                "## Project Context\n\n"
                "Read this section to understand the project BEFORE exploring code.\n"
                "It describes the tech stack, directory structure, key files, and entry points.\n"
                "Use this to navigate efficiently — read only the files relevant to your task.\n\n"
                + context_doc
            )
    else:
        return TaskStatus.FAILED, "Task has no target model or agent configured"

    cmd = build_claude_command(
        task, project_root, system_prompt=system_prompt, model_override=model_flag,
        ignore_model=ignore_model,
    )

    if dry_run:
        model_label = "default" if ignore_model else model_flag
        if task.target_agent:
            agent_label = f"agent:{task.target_agent}"
        elif task.agent_role:
            agent_label = f"role:{task.agent_role.value}"
        else:
            agent_label = f"model:{model_label}"
        console.print(
            f"  [dim][{agent_label}] $ claude --print --model {model_label} ... '{task.prompt[:60]}...'[/dim]"
        )
        return TaskStatus.DONE, "[dry-run]"

    try:
        # Ignore SIGINT in the child process so Ctrl+C doesn't kill the running task.
        # The parent catches SIGINT via ShutdownManager and stops AFTER this task finishes.
        process = subprocess.Popen(
            cmd,
            cwd=str(project_root / "app"),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            preexec_fn=lambda: signal.signal(signal.SIGINT, signal.SIG_IGN),
        )

        stdout_lines: list[str] = []
        stderr_lines: list[str] = []

        # Read stderr in background to avoid deadlock
        def _drain_stderr() -> None:
            assert process.stderr is not None
            for line in process.stderr:
                stderr_lines.append(line)

        stderr_thread = threading.Thread(target=_drain_stderr, daemon=True)
        stderr_thread.start()

        # Stream stdout to console in real-time
        assert process.stdout is not None
        for line in process.stdout:
            stdout_lines.append(line)
            console.print(line, end="", highlight=False, markup=False)

        stderr_thread.join()
        process.wait()

        full_stdout = "".join(stdout_lines)
        full_stderr = "".join(stderr_lines)

        if process.returncode == 0:
            return TaskStatus.DONE, full_stdout[:500]
        else:
            error = full_stderr[:500] if full_stderr else full_stdout[:500]
            return TaskStatus.FAILED, error

    except FileNotFoundError:
        return TaskStatus.FAILED, "claude CLI not found. Is it installed and in PATH?"


def run_phase(
    phase_num: int,
    project_root: Path,
    shutdown: ShutdownManager,
    state: StateManager,
    display: ProgressDisplay,
    dry_run: bool = False,
    ignore_model: bool = False,
) -> bool:
    """Run all pending tasks in a phase. Returns True if phase completed."""
    phase = state.load_phase(phase_num)
    total = len(phase.tasks)

    while True:
        task = state.next_pending_task(phase)
        if task is None:
            break

        if shutdown.should_stop:
            console.print("\n[yellow]Shutdown requested. Saving state...[/yellow]")
            state.save_phase(phase)
            return False

        if state.is_paused():
            console.print("\n[yellow]Paused. Resume with: orai run --resume[/yellow]")
            state.save_phase(phase)
            return False

        done_count = sum(1 for t in phase.tasks if t.status == TaskStatus.DONE)
        display.update(phase_num, task.id, task.description, done_count, total)

        task.status = TaskStatus.RUNNING
        task.started_at = datetime.now(timezone.utc)
        state.save_phase(phase)

        new_status, output = execute_task(task, project_root, dry_run, ignore_model)

        task.status = new_status
        task.completed_at = datetime.now(timezone.utc)
        if new_status == TaskStatus.DONE:
            task.output_summary = output
        else:
            task.error = output
            console.print(f"\n[red]Task {task.id} failed: {output}[/red]")

        state.save_phase(phase)

    # Final update: show completed progress
    done_count = sum(1 for t in phase.tasks if t.status == TaskStatus.DONE)
    failed_count = sum(1 for t in phase.tasks if t.status == TaskStatus.FAILED)
    display.update(phase_num, "—", "All tasks processed", done_count, total)

    if failed_count:
        console.print(
            f"\n[bold yellow]Phase {phase_num} finished: "
            f"{done_count}/{total} done, {failed_count} failed.[/bold yellow]"
        )
    else:
        console.print(
            f"\n[bold green]Phase {phase_num} completed: "
            f"{done_count}/{total} tasks done.[/bold green]"
        )

    return failed_count == 0 and done_count == total


def run_single_task(
    task_id: str,
    project_root: Path,
    state: StateManager,
    dry_run: bool = False,
    ignore_model: bool = False,
) -> None:
    """Run a single task by ID."""
    phase_num = int(task_id.split(".")[0])
    phase = state.load_phase(phase_num)

    task = next((t for t in phase.tasks if t.id == task_id), None)
    if task is None:
        console.print(f"[red]Task {task_id} not found in phase {phase_num}.[/red]")
        return

    if task.status not in (TaskStatus.PENDING, TaskStatus.FAILED):
        console.print(f"[yellow]Task {task_id} is {task.status.value}, skipping.[/yellow]")
        return

    console.print(f"[cyan]Running task {task_id}: {task.description}[/cyan]")

    task.status = TaskStatus.RUNNING
    task.started_at = datetime.now(timezone.utc)
    state.save_phase(phase)

    new_status, output = execute_task(task, project_root, dry_run, ignore_model)

    task.status = new_status
    task.completed_at = datetime.now(timezone.utc)
    if new_status == TaskStatus.DONE:
        task.output_summary = output
        console.print(f"[green]Task {task_id} completed.[/green]")
    else:
        task.error = output
        console.print(f"[red]Task {task_id} failed: {output}[/red]")

    state.save_phase(phase)


def run_project(
    project_root: Path,
    phase_num: Optional[int] = None,
    task_id: Optional[str] = None,
    resume: bool = False,
    dry_run: bool = False,
    ignore_model: bool = False,
) -> None:
    """Main entry point for running tasks."""
    state = StateManager(project_root)

    if resume:
        state.clear_pause()

    if task_id is not None:
        run_single_task(task_id, project_root, state, dry_run, ignore_model)
        return

    meta = state.load_project_meta()
    phases_to_run = [phase_num] if phase_num else meta.phases

    if not phases_to_run:
        console.print("[yellow]No phases found. Run 'orai plan' first.[/yellow]")
        return

    shutdown = ShutdownManager()
    shutdown.install()
    display = ProgressDisplay()

    try:
        display.start()
        for pn in phases_to_run:
            console.print(f"\n[bold cyan]Phase {pn}[/bold cyan]")
            completed = run_phase(pn, project_root, shutdown, state, display, dry_run, ignore_model)
            if not completed:
                break

            meta.current_phase = pn + 1
            state.save_project_meta(meta)
        else:
            console.print("\n[bold green]All phases completed![/bold green]")
    finally:
        display.stop()
        shutdown.uninstall()


def capture_task_artifacts(task: Task, project_root: Path, output: str) -> None:
    """After a task completes successfully, write a summary to the KB."""
    state = StateManager(project_root)
    summary_path = f"task-outputs/task-{task.id}-output.md"
    content = (
        f"# Task {task.id} Output\n\n"
        f"**Description**: {task.description}\n"
        f"**Status**: {task.status.value}\n"
        f"**Artifacts produced**: {', '.join(task.artifacts_produced) if task.artifacts_produced else 'none listed'}\n\n"
        f"## Summary\n\n{output[:1000] if output else 'No output captured.'}\n"
    )
    state.write_kb_doc(
        summary_path,
        content,
        title=f"Task {task.id} output",
        produced_by_task=task.id,
    )

    # Update task's artifacts_produced if the output mentions files
    file_mentions = re.findall(r"(?:created|wrote|modified|updated)\s+`?([^`\s]+\.\w+)`?", output)
    if file_mentions:
        task.artifacts_produced = list(set(file_mentions))


def run_tester_feedback_loop(
    phase: Phase,
    project_root: Path,
    shutdown: ShutdownManager,
    state: StateManager,
    display: ProgressDisplay,
    dry_run: bool = False,
    ignore_model: bool = False,
    max_retries: int = 3,
) -> None:
    """Run tester tasks for the phase. If bugs found, create retry tasks and re-run.

    After implementation tasks complete, tester agents review the work.
    If bugs are found, new tasks are created for the original agents to fix them.
    This loop repeats up to max_retries times.
    """
    from datetime import datetime, timezone

    retry_iteration = 0
    while retry_iteration < max_retries:
        # Collect tasks that need testing (done implementation tasks in this phase)
        done_tasks = [
            t for t in phase.tasks
            if t.status == TaskStatus.DONE and t.agent_role in (
                AgentRole.BACKEND, AgentRole.FRONTEND
            )
        ]
        if not done_tasks:
            return

        # Check for tester tasks already in the phase
        tester_tasks = [
            t for t in phase.tasks
            if t.agent_role == AgentRole.TESTER
            and t.status == TaskStatus.PENDING
            and all(d in {t2.id for t2 in phase.tasks if t2.status == TaskStatus.DONE} for d in t.depends_on)
        ]

        if not tester_tasks:
            # No tester tasks defined — skip feedback loop
            return

        console.print(f"\n[bold magenta]Tester feedback loop — iteration {retry_iteration + 1}[/bold magenta]")

        for tester_task in tester_tasks:
            if shutdown.should_stop:
                console.print("\n[yellow]Shutdown requested. Saving state...[/yellow]")
                state.save_phase(phase)
                return

            tester_task.status = TaskStatus.RUNNING
            tester_task.started_at = datetime.now(timezone.utc)
            state.save_phase(phase)

            new_status, output = execute_task(tester_task, project_root, dry_run, ignore_model)

            tester_task.status = new_status
            tester_task.completed_at = datetime.now(timezone.utc)
            if new_status == TaskStatus.DONE:
                tester_task.output_summary = output
            else:
                tester_task.error = output

            state.save_phase(phase)

            # Check if the tester produced a bug report
            bug_report = state.read_kb_doc(f"task-outputs/bug-{tester_task.task_id if hasattr(tester_task, 'task_id') else tester_task.id}.md")
            if bug_report and "critical" in bug_report.lower() or "major" in bug_report.lower():
                console.print(f"[yellow]Tester found bugs in task {tester_task.id}. Creating fix tasks...[/yellow]")
                # The tester should have written bug reports; parse them for task references
                retry_iteration += 1
                break
        else:
            # All tester tasks completed without finding critical bugs
            return

        retry_iteration += 1
