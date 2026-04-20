from __future__ import annotations

import re


def extract_skill_sections(skills_doc: str, skills: list[str]) -> str:
    """Extract ## sections matching the agent's skill names from Skills.md."""
    if not skills_doc or not skills:
        return ""

    pattern = re.compile(r"(?m)^## (.+)$")
    matches = list(pattern.finditer(skills_doc))
    if not matches:
        return ""

    sections: list[str] = []
    for i, match in enumerate(matches):
        section_name = match.group(1).strip()
        if section_name not in skills:
            continue
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(skills_doc)
        sections.append(skills_doc[start:end].rstrip())

    return "\n\n".join(sections)


def filter_scripts_section(section_text: str, scripts: list[str]) -> str:
    """Within a skill section, keep only ### entries for the agent's scripts."""
    if not scripts:
        return section_text

    h3_pattern = re.compile(r"(?m)^### (.+)$")
    h3_matches = list(h3_pattern.finditer(section_text))
    if not h3_matches:
        return section_text

    # Keep intro prose (before first ###)
    intro = section_text[: h3_matches[0].start()].rstrip()
    kept_parts = [intro]

    for i, match in enumerate(h3_matches):
        script_name = match.group(1).strip()
        if script_name not in scripts:
            continue
        start = match.start()
        end = h3_matches[i + 1].start() if i + 1 < len(h3_matches) else len(section_text)
        kept_parts.append(section_text[start:end].rstrip())

    return "\n\n".join(p for p in kept_parts if p)
