from __future__ import annotations

import json
import subprocess
import textwrap
from pathlib import Path
from typing import Optional

from orai.config import (
    CONTEXT_DOC_FILE,
    KB_DIR,
    KB_INDEX_FILE,
    KB_ARCHITECTURE_DIR,
    KB_DECISIONS_DIR,
    KB_PHASES_DIR,
    KB_AGENT_CONTEXTS_DIR,
    KB_SHARED_DIR,
    KB_TASK_OUTPUTS_DIR,
)

# Files that provide high-value project understanding (checked in order)
KEY_DOC_FILES = [
    "CLAUDE.md",
    "README.md",
    "README",
    "docs/README.md",
    "docs/ARCHITECTURE.md",
    "ARCHITECTURE.md",
    "CONTRIBUTING.md",
]

# Config files that reveal tech stack and dependencies
CONFIG_FILES = [
    "package.json",
    "pyproject.toml",
    "Cargo.toml",
    "go.mod",
    "Gemfile",
    "pom.xml",
    "build.gradle",
    "requirements.txt",
    "composer.json",
]

# Entry point patterns (files agents should read first for different task types)
ENTRY_POINT_PATTERNS = [
    "src/**/main.*",
    "src/**/app.*",
    "src/**/index.*",
    "app/layout.*",
    "app/page.*",
    "src/app/layout.*",
    "src/app/page.*",
    "src/**/routes.*",
    "src/**/urls.*",
    "src/**/schema.*",
    "src/**/models.*",
    "src/**/config.*",
]

# Directories to skip when building tree
IGNORED_DIRS = {
    "node_modules", ".git", ".next", "__pycache__", ".venv", "venv",
    "dist", "build", ".cache", ".turbo", "coverage", ".mypy_cache",
    ".pytest_cache", ".ruff_cache", "target", ".agents",
}

# Max depth for directory tree
MAX_TREE_DEPTH = 4

# Max lines to read from a doc file for the summary
MAX_DOC_LINES = 80


def _build_dir_tree(root: Path, prefix: str = "", depth: int = 0) -> list[str]:
    """Build a concise directory tree string, respecting depth and ignore rules."""
    if depth >= MAX_TREE_DEPTH:
        return []

    lines: list[str] = []
    try:
        entries = sorted(root.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower()))
    except PermissionError:
        return []

    dirs = [e for e in entries if e.is_dir() and e.name not in IGNORED_DIRS]
    files = [e for e in entries if e.is_file()]

    # Show files at this level (limit to avoid noise)
    for f in files[:20]:
        lines.append(f"{prefix}{f.name}")
    if len(files) > 20:
        lines.append(f"{prefix}... and {len(files) - 20} more files")

    # Recurse into subdirs
    for d in dirs:
        lines.append(f"{prefix}{d.name}/")
        lines.extend(_build_dir_tree(d, prefix=prefix + "  ", depth=depth + 1))

    return lines


def _read_file_head(path: Path, max_lines: int = MAX_DOC_LINES) -> str:
    """Read the first N lines of a file, return empty string if unreadable."""
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        content = "\n".join(lines[:max_lines])
        if len(lines) > max_lines:
            content += f"\n... ({len(lines) - max_lines} more lines)"
        return content
    except (OSError, UnicodeDecodeError):
        return ""


def _detect_tech_stack(app_dir: Path) -> dict:
    """Detect technology stack from config files."""
    stack: dict = {}

    pkg_json = app_dir / "package.json"
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
            if "tailwindcss" in deps:
                stack["css"] = "Tailwind CSS"
            if "prisma" in deps or "@prisma/client" in deps:
                stack["orm"] = "Prisma"
            if "drizzle-orm" in deps:
                stack["orm"] = "Drizzle"
            if "typescript" in deps:
                stack["language"] = "TypeScript"
        except (json.JSONDecodeError, OSError):
            pass

    pyproject = app_dir / "pyproject.toml"
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

    return stack


def _find_entry_points(app_dir: Path) -> list[str]:
    """Find key entry point files that agents should read first."""
    found: list[str] = []
    for pattern in ENTRY_POINT_PATTERNS:
        for match in sorted(app_dir.glob(pattern)):
            rel = str(match.relative_to(app_dir))
            if rel not in found:
                found.append(rel)
    return found[:15]  # cap to avoid noise


def generate_context(project_root: Path) -> str:
    """Scan the project and generate a context document for AI agents.

    Returns the markdown content of the context document.
    """
    app_dir = project_root / "app"
    if not app_dir.exists():
        app_dir = project_root  # fallback for non-orai projects

    sections: list[str] = []

    # --- Header ---
    sections.append(
        "# Project Context\n\n"
        "This document gives AI agents a quick understanding of the project.\n"
        "Read this FIRST before exploring code. It tells you what exists,\n"
        "where things live, and which files to read for specific tasks."
    )

    # --- Tech Stack ---
    stack = _detect_tech_stack(app_dir)
    if stack:
        lines = ["## Tech Stack\n"]
        for key, val in stack.items():
            lines.append(f"- **{key}**: {val}")
        sections.append("\n".join(lines))

    # --- Directory Structure ---
    tree_lines = _build_dir_tree(app_dir)
    if tree_lines:
        sections.append(
            "## Directory Structure\n\n```\n"
            + "\n".join(tree_lines)
            + "\n```"
        )

    # --- Key Documentation ---
    docs_found: list[tuple[str, str]] = []
    for doc_name in KEY_DOC_FILES:
        # Check both project root and app dir
        for base in [project_root, app_dir]:
            doc_path = base / doc_name
            if doc_path.exists():
                content = _read_file_head(doc_path)
                if content:
                    rel = str(doc_path.relative_to(project_root))
                    docs_found.append((rel, content))
                break  # don't read same doc from both locations

    if docs_found:
        lines = ["## Key Documentation\n"]
        for rel_path, content in docs_found:
            lines.append(f"### {rel_path}\n")
            lines.append(f"```markdown\n{content}\n```\n")
        sections.append("\n".join(lines))

    # --- Config Files ---
    configs_found: list[tuple[str, str]] = []
    for cfg_name in CONFIG_FILES:
        for base in [app_dir, project_root]:
            cfg_path = base / cfg_name
            if cfg_path.exists():
                content = _read_file_head(cfg_path, max_lines=50)
                if content:
                    rel = str(cfg_path.relative_to(project_root))
                    configs_found.append((rel, content))
                break

    if configs_found:
        lines = ["## Config Files\n"]
        for rel_path, content in configs_found:
            lines.append(f"### {rel_path}\n")
            lines.append(f"```\n{content}\n```\n")
        sections.append("\n".join(lines))

    # --- Entry Points ---
    entry_points = _find_entry_points(app_dir)
    if entry_points:
        lines = [
            "## Key Entry Points\n",
            "These are the most important files to read when starting a task:\n",
        ]
        for ep in entry_points:
            lines.append(f"- `{ep}`")
        sections.append("\n".join(lines))

    return "\n\n".join(sections)


def generate_and_save_context(project_root: Path) -> Path:
    """Generate context document and save it to .agents/CONTEXT.md.

    Returns the path to the saved file.
    """
    content = generate_context(project_root)

    app_dir = project_root / "app"
    if not app_dir.exists():
        app_dir = project_root

    output_path = app_dir / CONTEXT_DOC_FILE
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")

    return output_path


# =============================================================================
# Knowledge Base (Document Graph)
# =============================================================================

KB_SUBDIRS = [
    KB_DIR,
    KB_ARCHITECTURE_DIR,
    KB_DECISIONS_DIR,
    KB_PHASES_DIR,
    KB_AGENT_CONTEXTS_DIR,
    KB_SHARED_DIR,
    KB_TASK_OUTPUTS_DIR,
]


def ensure_kb_structure(app_dir: Path) -> None:
    """Create the full kb/ directory structure under app/.agents/."""
    base = app_dir
    for subdir in KB_SUBDIRS:
        (base / subdir).mkdir(parents=True, exist_ok=True)

    index_path = base / KB_INDEX_FILE
    if not index_path.exists():
        index_path.write_text("[]", encoding="utf-8")


def _kb_base(app_dir: Path) -> Path:
    """Return the kb base path for a project."""
    return app_dir


def _load_index(app_dir: Path) -> list[dict]:
    """Load the KB index from _index.json."""
    index_path = app_dir / KB_INDEX_FILE
    if index_path.exists():
        return json.loads(index_path.read_text(encoding="utf-8"))
    return []


def _save_index(app_dir: Path, index: list[dict]) -> None:
    """Save the KB index to _index.json."""
    index_path = app_dir / KB_INDEX_FILE
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text(json.dumps(index, indent=2), encoding="utf-8")


def save_kb_document(
    app_dir: Path,
    rel_path: str,
    content: str,
    title: str = "",
    description: str = "",
    produced_by_task: str = "",
    consumed_by_roles: list[str] | None = None,
) -> Path:
    """Write a document to the kb/ tree and register it in _index.json.

    Args:
        app_dir: the project's app/ directory
        rel_path: path relative to kb/ (e.g. "architecture/ARCHITECTURE.md")
        content: file content
        title: human-readable title
        description: short description of the document's purpose
        produced_by_task: task_id that created this document
        consumed_by_roles: list of AgentRole values that should read this doc
    """
    full_path = app_dir / KB_DIR / rel_path
    full_path.parent.mkdir(parents=True, exist_ok=True)
    full_path.write_text(content, encoding="utf-8")

    index = _load_index(app_dir)
    # Update existing entry or add new one
    for entry in index:
        if entry["path"] == rel_path:
            entry["title"] = title or entry.get("title", rel_path)
            entry["description"] = description or entry.get("description", "")
            entry["produced_by_task"] = produced_by_task or entry.get("produced_by_task", "")
            if consumed_by_roles:
                entry["consumed_by_roles"] = consumed_by_roles
            break
    else:
        index.append({
            "path": rel_path,
            "title": title or rel_path,
            "description": description,
            "produced_by_task": produced_by_task,
            "consumed_by_roles": consumed_by_roles or [],
        })
    _save_index(app_dir, index)
    return full_path


def load_kb_document(app_dir: Path, rel_path: str) -> str:
    """Read a single document from the kb/ tree. Returns empty string if missing."""
    full_path = app_dir / KB_DIR / rel_path
    try:
        return full_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def build_targeted_context(app_dir: Path, doc_paths: list[str]) -> str:
    """Assemble a targeted context document from specific kb/ paths.

    Only includes the documents listed in doc_paths, making the context
    much smaller than the monolithic CONTEXT.md.
    """
    sections: list[str] = []
    for rel_path in doc_paths:
        content = load_kb_document(app_dir, rel_path)
        if content:
            sections.append(f"## Reference: {rel_path}\n\n{content}")
    return "\n\n".join(sections) if sections else ""


def build_agent_context(app_dir: Path, role: str) -> str:
    """Build role-specific context from kb/agent-contexts/ and shared docs.

    Always includes:
    - kb/agent-contexts/{role}-context.md (if exists)
    - ARCHITECTURE.md (if exists and role != architect)
    - kb/shared/tdd-guidelines.md (if exists)
    """
    sections: list[str] = []

    role_context = load_kb_document(app_dir, f"agent-contexts/{role}-context.md")
    if role_context:
        sections.append(f"## Role Context: {role}\n\n{role_context}")

    if role != "architect":
        arch = load_kb_document(app_dir, "architecture/ARCHITECTURE.md")
        if arch:
            sections.append("## Architecture\n\n" + arch[:3000])

    tdd = load_kb_document(app_dir, "shared/tdd-guidelines.md")
    if tdd:
        sections.append("## TDD Guidelines\n\n" + tdd)

    return "\n\n".join(sections) if sections else ""


def get_kb_index(app_dir: Path) -> list[dict]:
    """Return the current KB index (list of document metadata dicts)."""
    return _load_index(app_dir)


def list_kb_documents(app_dir: Path, role: str | None = None) -> list[dict]:
    """List KB documents, optionally filtered by consuming role."""
    index = _load_index(app_dir)
    if role:
        return [
            entry for entry in index
            if not entry.get("consumed_by_roles")
            or role in entry["consumed_by_roles"]
        ]
    return index
