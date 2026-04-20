from pathlib import Path

AGENTS_DIR = ".agents"
TASKS_DIR = f"{AGENTS_DIR}/tasks"
PAUSE_SENTINEL = f"{AGENTS_DIR}/pause"
PROJECT_META_FILE = f"{AGENTS_DIR}/project.json"

DEFAULT_TEMPLATE = "nextjs"
SUPPORTED_TEMPLATES = ("nextjs", "python", "node", "go")

DEFAULT_MAX_BUDGET_USD = 1.0
DEFAULT_TASK_TIMEOUT = 600  # seconds

DEFAULT_ALLOWED_TOOLS = ["Bash", "Edit", "Read", "Write", "Glob", "Grep"]

ANSWERS_FILE = f"{AGENTS_DIR}/answers.json"
AGENTS_CONFIG_FILE = f"{AGENTS_DIR}/agents.json"
SKILLS_DOC_FILE = f"{AGENTS_DIR}/Skills.md"
CONTEXT_DOC_FILE = f"{AGENTS_DIR}/CONTEXT.md"
PLAN_STATE_FILE = f"{AGENTS_DIR}/plan_state.json"
ORCHESTRATION_CONFIG_FILE = f"{AGENTS_DIR}/orchestration.json"
SCRIPTS_DIR = f"{AGENTS_DIR}/scripts"

# Knowledge Base directories
KB_DIR = f"{AGENTS_DIR}/kb"
KB_INDEX_FILE = f"{AGENTS_DIR}/kb/_index.json"
KB_ARCHITECTURE_DIR = f"{AGENTS_DIR}/kb/architecture"
KB_DECISIONS_DIR = f"{AGENTS_DIR}/kb/architecture/decisions"
KB_PHASES_DIR = f"{AGENTS_DIR}/kb/phases"
KB_AGENT_CONTEXTS_DIR = f"{AGENTS_DIR}/kb/agent-contexts"
KB_SHARED_DIR = f"{AGENTS_DIR}/kb/shared"
KB_TASK_OUTPUTS_DIR = f"{AGENTS_DIR}/kb/task-outputs"

MODEL_FLAGS = {
    "haiku": "haiku",
    "sonnet": "sonnet",
    "opus": "opus",
}

TEMPLATES_DIR = Path(__file__).parent / "scaffold" / "templates"
PROMPTS_DIR = Path(__file__).parent / "prompts"
