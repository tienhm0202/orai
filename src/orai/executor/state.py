from __future__ import annotations

from pathlib import Path
from typing import Optional

from orai.config import (
    AGENTS_CONFIG_FILE,
    CONTEXT_DOC_FILE,
    KB_INDEX_FILE,
    KB_DIR,
    ORCHESTRATION_CONFIG_FILE,
    PAUSE_SENTINEL,
    PLAN_STATE_FILE,
    PROJECT_META_FILE,
    SKILLS_DOC_FILE,
    TASKS_DIR,
)
from orai.models import AgentProfile, AgentRole, AgentsConfig, OrchestrationConfig, Phase, PlanState, ProjectMeta, Task, TaskStatus


class StateManager:
    def __init__(self, project_root: Path):
        self.project_root = project_root
        # Detect which .agents/ layout is in use:
        # - Existing projects (orai init): .agents/ is under app/
        # - Imported projects (orai init -e): .agents/ is at project root
        app_agents = project_root / "app" / ".agents"
        root_agents = project_root / ".agents"
        if root_agents.exists():
            self.agents_dir = project_root
        elif app_agents.exists():
            self.agents_dir = project_root / "app"
        else:
            self.agents_dir = project_root / "app"  # default for new projects
        self.app_dir = self.agents_dir
        self.tasks_dir = self.app_dir / TASKS_DIR

    def load_phase(self, phase_num: int) -> Phase:
        path = self.tasks_dir / f"phase{phase_num}.json"
        if not path.exists():
            raise FileNotFoundError(f"Phase file not found: {path}")
        return Phase.model_validate_json(path.read_text())

    def save_phase(self, phase: Phase) -> None:
        self.tasks_dir.mkdir(parents=True, exist_ok=True)
        path = self.tasks_dir / f"phase{phase.phase_number}.json"
        path.write_text(phase.model_dump_json(indent=2))

    def load_project_meta(self) -> ProjectMeta:
        path = self.app_dir / PROJECT_META_FILE
        if not path.exists():
            raise FileNotFoundError(f"Project meta not found: {path}")
        return ProjectMeta.model_validate_json(path.read_text())

    def save_project_meta(self, meta: ProjectMeta) -> None:
        path = self.app_dir / PROJECT_META_FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(meta.model_dump_json(indent=2))

    def is_paused(self) -> bool:
        return (self.app_dir / PAUSE_SENTINEL).exists()

    def set_pause(self) -> None:
        sentinel = self.app_dir / PAUSE_SENTINEL
        sentinel.parent.mkdir(parents=True, exist_ok=True)
        sentinel.touch()

    def clear_pause(self) -> None:
        sentinel = self.app_dir / PAUSE_SENTINEL
        sentinel.unlink(missing_ok=True)

    def load_agents_config(self) -> AgentsConfig:
        path = self.app_dir / AGENTS_CONFIG_FILE
        if not path.exists():
            return AgentsConfig(agents=[])
        return AgentsConfig.model_validate_json(path.read_text())

    def save_agents_config(self, config: AgentsConfig) -> None:
        path = self.app_dir / AGENTS_CONFIG_FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(config.model_dump_json(indent=2))

    def load_skills_doc(self) -> str:
        path = self.app_dir / SKILLS_DOC_FILE
        if not path.exists():
            return ""
        return path.read_text()

    def load_context_doc(self) -> str:
        path = self.app_dir / CONTEXT_DOC_FILE
        if not path.exists():
            return ""
        return path.read_text()

    def skill_section_exists(self, skill_name: str) -> bool:
        """Check if a ## skill section already exists in Skills.md."""
        import re

        doc = self.load_skills_doc()
        if not doc:
            return False
        pattern = re.compile(r"(?m)^## " + re.escape(skill_name) + r"\s*$")
        return bool(pattern.search(doc))

    def append_skill_section(self, skill_name: str, content: str) -> None:
        """Append a new ## skill section to Skills.md."""
        path = self.app_dir / SKILLS_DOC_FILE
        existing = path.read_text() if path.exists() else ""
        section = f"\n\n---\n\n## {skill_name}\n\n{content}\n"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(existing + section)

    def resolve_agent(self, name: str) -> Optional[AgentProfile]:
        config = self.load_agents_config()
        for agent in config.agents:
            if agent.name == name:
                return agent
        return None

    def resolve_agent_by_role(self, role: AgentRole) -> Optional[AgentProfile]:
        """Find the agent that matches a given role."""
        config = self.load_agents_config()
        for agent in config.agents:
            if agent.role == role:
                return agent
        return None

    def load_orchestration_config(self) -> Optional[OrchestrationConfig]:
        path = self.app_dir / ORCHESTRATION_CONFIG_FILE
        if not path.exists():
            return None
        return OrchestrationConfig.model_validate_json(path.read_text())

    # --- Knowledge Base methods ---

    def load_kb_index(self) -> list[dict]:
        """Load the KB document graph index."""
        path = self.app_dir / KB_INDEX_FILE
        if not path.exists():
            return []
        import json
        return json.loads(path.read_text())

    def save_kb_index(self, index: list[dict]) -> None:
        """Save the KB document graph index."""
        path = self.app_dir / KB_INDEX_FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        import json
        path.write_text(json.dumps(index, indent=2))

    def read_kb_doc(self, rel_path: str) -> str:
        """Read a single document from the kb/ tree. Empty string if missing."""
        from orai.planner.context import load_kb_document
        return load_kb_document(self.app_dir, rel_path)

    def write_kb_doc(self, rel_path: str, content: str, **kwargs) -> Path:
        """Write a document to the kb/ tree and update index."""
        from orai.planner.context import save_kb_document
        return save_kb_document(self.app_dir, rel_path, content, **kwargs)

    def next_pending_task(self, phase: Phase) -> Optional[Task]:
        """Return the first pending task whose dependencies are all done.

        Dependencies may reference tasks in earlier phases, so collect
        done IDs from both the current phase and all prior phases.
        """
        done_ids = {t.id for t in phase.tasks if t.status == TaskStatus.DONE}

        # Include done tasks from earlier phases so cross-phase deps resolve.
        for pn in range(1, phase.phase_number):
            try:
                earlier = self.load_phase(pn)
                done_ids.update(t.id for t in earlier.tasks if t.status == TaskStatus.DONE)
            except FileNotFoundError:
                continue

        for t in sorted(phase.tasks, key=lambda t: t.priority):
            if t.status == TaskStatus.PENDING and all(
                d in done_ids for d in t.depends_on
            ):
                return t
        return None

    def save_plan_state(self, plan_state: PlanState) -> None:
        path = self.app_dir / PLAN_STATE_FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(plan_state.model_dump_json(indent=2))

    def load_plan_state(self) -> Optional[PlanState]:
        path = self.app_dir / PLAN_STATE_FILE
        if not path.exists():
            return None
        return PlanState.model_validate_json(path.read_text())
