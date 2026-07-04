"""SKILL.md progressive disclosure loader."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from constants import get_emperor_home


@dataclass
class Skill:
    name: str
    path: Path
    description: str
    body: str
    source: str = "unknown"


def _parse_skill_md(path: Path) -> Skill | None:
    text = path.read_text(encoding="utf-8", errors="replace")
    name = path.parent.name
    description = ""
    body = text
    for line in text.splitlines()[:20]:
        if line.startswith("description:"):
            description = line.split(":", 1)[1].strip()
            break
    return Skill(name=name, path=path, description=description or name, body=body)


def discover_skills(
    *,
    project_dir: Path | None = None,
    home: Path | None = None,
) -> list[Skill]:
    """Discover SKILL.md files in project and user skill dirs."""
    dirs: list[Path] = []
    if project_dir:
        dirs.append(project_dir / "skills")
    home_root = home or get_emperor_home()
    dirs.append(home_root / "skills")
    dirs.append(Path(__file__).resolve().parents[2] / "skills")

    skills: dict[str, Skill] = {}
    for base in dirs:
        if not base.is_dir():
            continue
        for skill_md in base.glob("**/SKILL.md"):
            skill = _parse_skill_md(skill_md)
            if skill:
                if project_dir and skill_md.is_relative_to(project_dir):
                    skill.source = "project"
                elif skill_md.is_relative_to(home_root):
                    skill.source = "user"
                else:
                    skill.source = "builtin"
                skills[skill.name] = skill
    return list(skills.values())


def skills_summary(skills: list[Skill], *, max_body: int = 500) -> str:
    """Build progressive disclosure summary for prompt."""
    lines: list[str] = []
    for s in skills:
        preview = s.body[:max_body].replace("\n", " ")
        lines.append(f"- **{s.name}**: {s.description}\n  {preview}...")
    return "\n".join(lines) if lines else ""
