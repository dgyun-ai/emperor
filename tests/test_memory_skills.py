"""Tests for memory and skills."""

from __future__ import annotations

import pytest

from memory.manager import MemoryManager
from memory.fts import MemoryFTS
from skills.curator import SkillsCurator
from skills.loader import discover_skills
from skills.recommender import recommend_skills_for_query


def test_memory_manager(tmp_path):
    mgr = MemoryManager(home=tmp_path)
    mgr.write_memory("remember this")
    mgr.append_memory("more")
    assert "remember" in mgr.read_memory()
    assert mgr.summary_for_prompt()


def test_memory_user_profile(tmp_path):
    mgr = MemoryManager(home=tmp_path)
    mgr.write_user("likes Python")
    assert "Python" in mgr.read_user()


@pytest.mark.asyncio
async def test_memory_fts(tmp_path):
    fts = MemoryFTS(db_path=tmp_path / "mem.db")
    await fts.initialize()
    await fts.index("MEMORY.md", "user prefers dark mode")
    results = await fts.search("dark")
    assert len(results) >= 1


def test_skills_curator(tmp_path):
    c = SkillsCurator(home=tmp_path)
    c.record_use("test-skill")
    stats = c.get_stats()
    assert stats["test-skill"]["count"] == 1


def test_discover_skills_empty():
    skills = discover_skills(project_dir=__import__("pathlib").Path("/nonexistent"))
    assert isinstance(skills, list)


def test_discover_skills_project_dir():
    project_dir = __import__("pathlib").Path(__file__).resolve().parents[1]
    skills = discover_skills(project_dir=project_dir)
    names = {skill.name for skill in skills}
    assert "frontend-ui-audit" in names
    assert "backend-api-debug" in names


def test_skill_recommendation_prefers_relevant_project_skill():
    project_dir = __import__("pathlib").Path(__file__).resolve().parents[1]
    skills = discover_skills(project_dir=project_dir)
    selected, result = recommend_skills_for_query(
        "Please debug my backend API 500 response and request validation issue",
        skills,
        host="emperor",
        limit=5,
    )
    names = [skill.name for skill in selected]
    assert "backend-api-debug" in names
    assert result is not None
    assert "Recommended skills for query" in result["context_summary_text"]
