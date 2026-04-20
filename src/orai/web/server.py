from __future__ import annotations

import asyncio
import hashlib
import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

import uvicorn
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, StreamingResponse
from jinja2 import Environment, FileSystemLoader

from orai.executor.state import StateManager
from orai.models import TaskStatus


def _compute_phase_status(phase) -> str:
    """Return one of: done, running, failed, pending."""
    if not phase.tasks:
        return "pending"
    if TaskStatus.FAILED in {t.status for t in phase.tasks}:
        return "failed"
    if all(t.status == TaskStatus.DONE for t in phase.tasks):
        return "done"
    if any(t.status == TaskStatus.RUNNING for t in phase.tasks):
        return "running"
    return "pending"


def _phase_summary(phase) -> dict:
    return {
        "phase_number": phase.phase_number,
        "title": phase.title,
        "status": _compute_phase_status(phase),
        "done": sum(1 for t in phase.tasks if t.status == TaskStatus.DONE),
        "total": len(phase.tasks),
        "failed": sum(1 for t in phase.tasks if t.status == TaskStatus.FAILED),
    }


def _task_row(task) -> dict:
    return {
        "id": task.id,
        "description": task.description,
        "status": task.status.value,
        "target_model": task.target_model.value if task.target_model else "—",
        "priority": task.priority,
        "error": task.error,
        "started_at": task.started_at.isoformat() if task.started_at else None,
        "completed_at": task.completed_at.isoformat() if task.completed_at else None,
    }


class SSEBroker:
    """Simple fan-out broker for SSE clients."""

    def __init__(self) -> None:
        self._queues: list[asyncio.Queue] = []

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=100)
        self._queues.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        if q in self._queues:
            self._queues.remove(q)

    async def publish(self, data: dict) -> None:
        payload = f"data: {json.dumps(data)}\n\n"
        for q in list(self._queues):
            try:
                q.put_nowait(payload)
            except asyncio.QueueFull:
                pass


broker = SSEBroker()


async def _watch_phases(
    state: StateManager, phase_numbers: list[int], interval: float = 2.0
) -> None:
    """Poll phase files and publish SSE events on change."""
    last_hashes: dict[int, str] = {}

    while True:
        for pn in phase_numbers:
            path = state.tasks_dir / f"phase{pn}.json"
            if not path.exists():
                continue
            raw = path.read_bytes()
            h = hashlib.sha256(raw).hexdigest()
            if last_hashes.get(pn) != h:
                last_hashes[pn] = h
                try:
                    phase = state.load_phase(pn)
                    await broker.publish({
                        "type": "phase_update",
                        "phase_number": pn,
                        "summary": _phase_summary(phase),
                        "tasks": [_task_row(t) for t in phase.tasks],
                    })
                except Exception:
                    pass
        await asyncio.sleep(interval)


def create_app(project_root: Path) -> FastAPI:
    state = StateManager(project_root)
    meta = state.load_project_meta()
    phase_numbers = meta.phases

    tpl_dir = Path(__file__).parent / "templates"
    jinja_env = Environment(loader=FileSystemLoader(str(tpl_dir)))

    app = FastAPI(title="orai UI")

    # Reset broker per app instance to avoid stale queues from previous runs
    broker._queues.clear()

    @app.get("/", response_class=HTMLResponse)
    async def index():
        tmpl = jinja_env.get_template("index.html")
        return tmpl.render(
            project_name=meta.name,
            project_root=project_root.name,
            phases=phase_numbers,
        )

    @app.get("/api/status")
    async def api_status():
        phases = [state.load_phase(n) for n in phase_numbers]
        total_tasks = sum(len(p.tasks) for p in phases)
        total_done = sum(1 for p in phases for t in p.tasks if t.status == TaskStatus.DONE)
        total_failed = sum(1 for p in phases for t in p.tasks if t.status == TaskStatus.FAILED)
        return {
            "project_name": meta.name,
            "project_folder": project_root.name,
            "project_type": meta.project_type,
            "current_phase": meta.current_phase,
            "overall": {
                "total": total_tasks,
                "done": total_done,
                "failed": total_failed,
                "pending": total_tasks - total_done - total_failed,
            },
            "phases": [_phase_summary(p) for p in phases],
        }

    @app.get("/api/phases")
    async def api_phases():
        phases = [state.load_phase(n) for n in phase_numbers]
        return [_phase_summary(p) for p in phases]

    @app.get("/api/phase/{phase_num}")
    async def api_phase(phase_num: int):
        phase = state.load_phase(phase_num)
        return {
            "phase_number": phase.phase_number,
            "title": phase.title,
            "description": phase.description,
            "validation": phase.validation,
            "status": _compute_phase_status(phase),
            "tasks": [_task_row(t) for t in phase.tasks],
        }

    @app.get("/api/sse")
    async def sse_stream():
        queue = broker.subscribe()
        try:
            async def event_generator() -> AsyncGenerator[str, None]:
                phases = [state.load_phase(n) for n in phase_numbers]
                init_data = {
                    "type": "init",
                    "phases": [_phase_summary(p) for p in phases],
                }
                yield f"data: {json.dumps(init_data)}\n\n"
                while True:
                    payload = await queue.get()
                    yield payload

            return StreamingResponse(
                event_generator(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                },
            )
        finally:
            broker.unsubscribe(queue)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        task = asyncio.create_task(_watch_phases(state, phase_numbers))
        yield
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    app.router.lifespan_context = lifespan

    return app


def start_ui(project_root: Path, port: int = 8888) -> None:
    """Launch the orai web UI."""
    project_root = project_root.resolve()
    app = create_app(project_root)
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")
