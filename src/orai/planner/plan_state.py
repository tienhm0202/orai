from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from orai.config import CONTEXT_DOC_FILE
from orai.executor.state import StateManager
from orai.models import PlanState, TaskStatus

TDD_GUIDELINES = (
    "TDD WORKFLOW: For every implementation task:\n"
    "1. Write tests FIRST that define expected behavior (unit tests, integration tests as appropriate)\n"
    "2. Implement code to make those tests pass\n"
    "3. Verify ALL tests pass before considering the task complete\n"
    "4. Refactor only after tests pass\n"
    "Do not skip the testing step. Write the tests before writing the implementation."
)


def generate_plan_state(project_root: Path) -> PlanState:
    """Generate a structured plan state file capturing project status and TDD guidelines."""
    state = StateManager(project_root)
    meta = state.load_project_meta()

    phases_summary = []
    next_tasks = []

    for phase_num in meta.phases:
        try:
            phase = state.load_phase(phase_num)
        except FileNotFoundError:
            phases_summary.append({
                "phase_number": phase_num,
                "title": "(phase file missing)",
                "total_tasks": 0,
                "done": 0,
                "failed": 0,
                "pending": 0,
            })
            continue

        done = sum(1 for t in phase.tasks if t.status == TaskStatus.DONE)
        failed = sum(1 for t in phase.tasks if t.status == TaskStatus.FAILED)
        pending = sum(1 for t in phase.tasks if t.status == TaskStatus.PENDING)

        phases_summary.append({
            "phase_number": phase.phase_number,
            "title": phase.title,
            "total_tasks": len(phase.tasks),
            "done": done,
            "failed": failed,
            "pending": pending,
        })

        next_task = state.next_pending_task(phase)
        if next_task:
            next_tasks.append({
                "id": next_task.id,
                "description": next_task.description,
                "phase": phase_num,
                "priority": next_task.priority,
                "depends_on": next_task.depends_on,
            })

    # Overall status
    total_tasks = sum(p["total_tasks"] for p in phases_summary)
    total_done = sum(p["done"] for p in phases_summary)
    if total_tasks > 0 and total_done == total_tasks:
        overall_status = "completed"
    elif total_done > 0:
        overall_status = "in_progress"
    else:
        overall_status = "not_started"

    # Context summary
    context_doc = state.load_context_doc()
    if context_doc:
        context_summary = context_doc[:500] + ("..." if len(context_doc) > 500 else "")
    else:
        context_summary = "No context document generated yet."

    return PlanState(
        project_name=meta.name,
        generated_at=datetime.now(timezone.utc),
        overall_status=overall_status,
        phases_summary=phases_summary,
        next_actionable_tasks=next_tasks,
        tdd_guidelines=TDD_GUIDELINES,
        project_context_summary=context_summary,
    )
