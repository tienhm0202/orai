from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, model_validator


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    PAUSED = "paused"
    SKIPPED = "skipped"


class TargetModel(str, Enum):
    HAIKU = "haiku"
    SONNET = "sonnet"
    OPUS = "opus"


class AgentRole(str, Enum):
    ARCHITECT = "architect"
    PROJECT_MANAGER = "project_manager"
    BACKEND = "backend"
    FRONTEND = "frontend"
    TESTER = "tester"


class LanguageStack(str, Enum):
    PYTHON = "python"
    NODE = "node"
    GO = "go"


class AgentProfile(BaseModel):
    name: str
    email: str
    role: AgentRole = AgentRole.BACKEND
    language_stack: Optional[LanguageStack] = None
    skills: list[str] = Field(default_factory=list)
    scripts: list[str] = Field(default_factory=list)
    model: TargetModel = TargetModel.SONNET
    system_prompt_template: str = ""


class AgentsConfig(BaseModel):
    agents: list[AgentProfile] = Field(default_factory=list)


class Task(BaseModel):
    id: str
    description: str
    prompt: str
    priority: int = Field(ge=1, le=100)
    target_model: Optional[TargetModel] = None
    target_agent: Optional[str] = None
    agent_role: Optional[AgentRole] = None
    status: TaskStatus = TaskStatus.PENDING
    depends_on: list[str] = Field(default_factory=list)
    allowed_tools: list[str] = Field(
        default_factory=lambda: ["Bash", "Edit", "Read", "Write", "Glob", "Grep"]
    )
    max_budget_usd: float = 1.0
    tdd_required: bool = True
    context_documents: list[str] = Field(default_factory=list)
    artifacts_produced: list[str] = Field(default_factory=list)
    retry_count: int = 0
    max_retries: int = 3
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error: Optional[str] = None
    output_summary: Optional[str] = None

    @model_validator(mode="after")
    def validate_target(self) -> "Task":
        if self.agent_role is not None:
            return self
        if self.target_model is None and self.target_agent is None:
            raise ValueError(
                "Task must specify either 'target_model' or 'target_agent'."
            )
        if self.target_model is not None and self.target_agent is not None:
            raise ValueError(
                "Task must specify only one of 'target_model' or 'target_agent', not both."
            )
        return self


class Phase(BaseModel):
    phase_number: int
    title: str
    description: str
    validation: str
    tasks: list[Task]


class ProjectMeta(BaseModel):
    name: str
    project_type: str
    created_at: datetime
    phases: list[int] = Field(default_factory=list)
    current_phase: int = 1


class PlanState(BaseModel):
    project_name: str
    generated_at: datetime
    overall_status: str
    phases_summary: list[dict]
    next_actionable_tasks: list[dict]
    tdd_guidelines: str
    project_context_summary: str


class DocumentRef(BaseModel):
    path: str
    title: str
    description: str
    produced_by_task: str = ""
    consumed_by_roles: list[str] = Field(default_factory=list)


class OrchestrationConfig(BaseModel):
    language_stack: LanguageStack = LanguageStack.PYTHON
    architecture_decisions: list[str] = Field(default_factory=list)
    architect_first: bool = True
    pm_enforces_tdd: bool = True
    tester_enabled: bool = True
    max_retry_loops: int = 3
