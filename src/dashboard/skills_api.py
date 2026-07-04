"""Skills management API."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from dashboard.context import get_workspace_root
from skills.loader import Skill, discover_skills

router = APIRouter(prefix="/api/skills", tags=["skills"])

_pinned: set[str] = set()


def _project_skills_dir() -> Path:
    root = get_workspace_root()
    project_dir = root.parent if root.name == "workspace" else root
    skills_dir = project_dir / "skills"
    skills_dir.mkdir(parents=True, exist_ok=True)
    return skills_dir


def _skill_to_dict(skill: Skill, *, include_body: bool = False) -> dict:
    payload = {
        "name": skill.name,
        "description": skill.description,
        "source": skill.source,
        "pinned": skill.name in _pinned,
        "path": str(skill.path),
    }
    if include_body:
        payload["body"] = skill.body
    else:
        payload["preview"] = skill.body[:500]
    return payload


def _find_skill(name: str) -> Skill | None:
    root = get_workspace_root()
    project_dir = root.parent if root.name == "workspace" else root
    for skill in discover_skills(project_dir=project_dir):
        if skill.name == name:
            return skill
    return None


def _assert_editable(skill: Skill) -> None:
    if skill.source == "builtin":
        raise HTTPException(403, "Built-in skills are read-only")


@router.get("")
async def list_skills():
    root = get_workspace_root()
    project_dir = root.parent if root.name == "workspace" else root
    skills = discover_skills(project_dir=project_dir)
    return {"skills": [_skill_to_dict(s) for s in skills]}


@router.get("/{name}")
async def get_skill(name: str):
    skill = _find_skill(name)
    if not skill:
        raise HTTPException(404, "Skill not found")
    return _skill_to_dict(skill, include_body=True)


class SkillCreateRequest(BaseModel):
    name: str
    description: str = ""
    body: str = ""


class SkillUpdateRequest(BaseModel):
    description: str | None = None
    body: str


def _default_skill_body(name: str, description: str) -> str:
    desc = description or name
    return f"---\ndescription: {desc}\n---\n\n# {name}\n"


@router.post("")
async def create_skill(req: SkillCreateRequest):
    name = req.name.strip()
    if not name:
        raise HTTPException(400, "Skill name is required")
    if _find_skill(name):
        raise HTTPException(409, "Skill already exists")
    body = req.body.strip() or _default_skill_body(name, req.description)
    target = _project_skills_dir() / name
    target.mkdir(parents=True, exist_ok=True)
    (target / "SKILL.md").write_text(body, encoding="utf-8")
    skill = _find_skill(name)
    if not skill:
        raise HTTPException(500, "Failed to create skill")
    return {"ok": True, **_skill_to_dict(skill, include_body=True)}


@router.put("/{name}")
async def update_skill(name: str, req: SkillUpdateRequest):
    skill = _find_skill(name)
    if not skill:
        raise HTTPException(404, "Skill not found")
    _assert_editable(skill)
    if skill.source == "user":
        target = Path(skill.path)
    else:
        target = _project_skills_dir() / name / "SKILL.md"
        target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(req.body, encoding="utf-8")
    updated = _find_skill(name)
    if not updated:
        raise HTTPException(500, "Failed to update skill")
    return {"ok": True, **_skill_to_dict(updated, include_body=True)}


class PinRequest(BaseModel):
    names: list[str] = Field(default_factory=list)


@router.post("/pin")
async def pin_skills(req: PinRequest):
    global _pinned
    _pinned = set(req.names)
    return {"ok": True, "pinned": list(_pinned)}


@router.delete("/{name}")
async def delete_skill(name: str):
    skill = _find_skill(name)
    if not skill:
        raise HTTPException(404, "Skill not found")
    _assert_editable(skill)
    skill_md = Path(skill.path)
    if skill_md.is_file():
        skill_md.unlink()
        parent = skill_md.parent
        if parent.is_dir() and not any(parent.iterdir()):
            parent.rmdir()
        return {"ok": True}
    raise HTTPException(404, "Skill not found")


@router.post("/import")
async def import_skill():
    return {"ok": False, "message": "Skill zip import not yet implemented; copy SKILL.md into workspace/skills/"}
