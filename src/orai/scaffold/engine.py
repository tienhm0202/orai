from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from orai.config import SUPPORTED_TEMPLATES, TEMPLATES_DIR, PROJECT_META_FILE
from orai.models import ProjectMeta


def scaffold(project_name: str, template: str, parent: Path) -> Path:
    """Create a new project from a template.

    Returns the project root path.
    """
    if template not in SUPPORTED_TEMPLATES:
        raise ValueError(
            f"Unknown template '{template}'. Choose from: {SUPPORTED_TEMPLATES}"
        )

    parent = parent.resolve()
    project_root = parent / project_name

    if project_root.exists():
        raise FileExistsError(f"Directory already exists: {project_root}")

    template_dir = TEMPLATES_DIR / template
    env = Environment(
        loader=FileSystemLoader(str(template_dir)),
        keep_trailing_newline=True,
    )

    # Load structure manifest
    structure_raw = (template_dir / "structure.json").read_text()
    # Render the structure.json itself (for {{ project_name }} in paths)
    structure_rendered = env.from_string(structure_raw).render(
        project_name=project_name, project_type=template
    )
    structure = json.loads(structure_rendered)

    context = {"project_name": project_name, "project_type": template}

    # Create directories
    for d in structure["dirs"]:
        (project_root / d).mkdir(parents=True, exist_ok=True)

    # Render and write files
    for target_path, template_name in structure["files"].items():
        tmpl = env.get_template(template_name)
        rendered = tmpl.render(context)
        dest = project_root / target_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(rendered)

    # Create project meta
    meta = ProjectMeta(
        name=project_name,
        project_type=template,
        created_at=datetime.now(timezone.utc),
    )
    meta_path = project_root / "app" / PROJECT_META_FILE
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.write_text(meta.model_dump_json(indent=2))

    return project_root
