from __future__ import annotations

from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from orai.models import AgentRole, Phase, ProjectMeta, TaskStatus


class ProgressDisplay:
    """Static header table with streaming subprocess output below."""

    def __init__(self) -> None:
        self.console = Console()

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass

    def update(
        self,
        phase: int,
        task_id: str,
        task_desc: str,
        done: int,
        total: int,
    ) -> None:
        """Print a task header banner. Logs from previous tasks stay in scroll."""
        self.console.print()
        self.console.rule(
            f"[bold cyan]Phase {phase}[/bold cyan] │ "
            f"[yellow]{task_id}[/yellow] — {task_desc[:40]} │ "
            f"[green]{done}/{total}[/green]",
            style="dim",
        )
        self.console.print()


STATUS_COLORS = {
    TaskStatus.PENDING: "dim",
    TaskStatus.RUNNING: "yellow",
    TaskStatus.DONE: "green",
    TaskStatus.FAILED: "red",
    TaskStatus.PAUSED: "yellow",
    TaskStatus.SKIPPED: "dim",
}


def print_status(meta: ProjectMeta, phases: list[Phase]) -> None:
    """Print a status table for all phases and tasks."""
    console = Console()

    console.print(f"\n[bold]{meta.name}[/bold] ({meta.project_type})\n")

    for phase in phases:
        done = sum(1 for t in phase.tasks if t.status == TaskStatus.DONE)
        failed = sum(1 for t in phase.tasks if t.status == TaskStatus.FAILED)
        total = len(phase.tasks)

        phase_color = "green" if done == total else "cyan"
        console.print(
            f"[bold {phase_color}]Phase {phase.phase_number}: "
            f"{phase.title}[/bold {phase_color}] — {done}/{total} done"
            + (f", {failed} failed" if failed else "")
        )

        table = Table(show_header=True, header_style="bold", box=None, padding=(0, 1))
        table.add_column("ID", width=6)
        table.add_column("Status", width=10)
        table.add_column("Agent", width=16)
        table.add_column("Description", width=50)

        for task in phase.tasks:
            color = STATUS_COLORS.get(task.status, "white")
            if task.target_model is not None:
                agent_label = task.target_model.value
            elif task.agent_role is not None:
                agent_label = task.agent_role.value
            elif task.target_agent:
                agent_label = task.target_agent
            else:
                agent_label = "unknown"
            table.add_row(
                task.id,
                f"[{color}]{task.status.value}[/{color}]",
                agent_label,
                task.description[:50],
            )

        console.print(table)
        console.print()

    # Summary
    total_tasks = sum(len(p.tasks) for p in phases)
    total_done = sum(
        1 for p in phases for t in p.tasks if t.status == TaskStatus.DONE
    )
    console.print(
        f"[bold]Overall: {total_done}/{total_tasks} tasks complete "
        f"across {len(phases)} phases[/bold]\n"
    )
