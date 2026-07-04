"""Project-local skill recommendation for prompt injection."""

from __future__ import annotations

from collections import Counter
from typing import Any

from skills.loader import Skill


def recommend_skills_for_query(
    query: str,
    skills: list[Skill],
    *,
    host: str = "emperor",
    limit: int = 10,
    token_budget: int | None = None,
) -> tuple[list[Skill], dict[str, Any] | None]:
    """Return relevant skills using project-local heuristics only."""
    if not query.strip() or not skills:
        return skills[:limit], None

    scored = [_score_skill(query, skill) for skill in skills]
    ranked = sorted(
        scored,
        key=lambda item: (
            item["score"],
            item["project_bonus"],
            item["match_count"],
            item["priority"],
            item["skill"].name,
        ),
        reverse=True,
    )
    selected_items = _apply_token_budget(ranked, limit=limit, token_budget=token_budget)
    selected = [item["skill"] for item in selected_items]
    result = _build_result(query, ranked, selected_items, host=host)
    if not selected:
        return skills[:limit], result
    return selected, result


def _score_skill(query: str, skill: Skill) -> dict[str, Any]:
    preview = skill.body[:600].replace("\n", " ").strip()
    haystack = f"{skill.name} {skill.description} {preview}".lower()
    terms = _query_terms(query)
    matches = Counter(term for term in terms if term in haystack)
    match_count = sum(matches.values())
    project_bonus = 2 if skill.source == "project" else 0
    priority = _priority_for_skill(skill, haystack)
    score = (match_count * 10) + project_bonus + priority
    return {
        "skill": skill,
        "score": score,
        "match_count": match_count,
        "matched_terms": sorted(matches.keys()),
        "project_bonus": project_bonus,
        "priority": priority,
        "preview": preview,
        "token_preview": max(20, len(preview) // 4),
    }


def _apply_token_budget(
    ranked: list[dict[str, Any]],
    *,
    limit: int,
    token_budget: int | None,
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    spent = 0
    for item in ranked:
        if len(selected) >= limit:
            break
        projected = spent + item["token_preview"]
        if token_budget is not None and selected and projected > token_budget:
            continue
        if token_budget is not None and not selected and item["token_preview"] > token_budget:
            continue
        selected.append(item)
        spent = projected
    return selected


def _build_result(
    query: str,
    ranked: list[dict[str, Any]],
    selected: list[dict[str, Any]],
    *,
    host: str,
) -> dict[str, Any]:
    selected_skills = [
        {
            "id": item["skill"].name,
            "name": item["skill"].name,
            "description": item["skill"].description,
            "path": str(item["skill"].path),
            "preview": _truncate_preview(item["preview"]),
            "score_breakdown": {
                "term_match": item["match_count"] * 10,
                "project_bonus": item["project_bonus"],
                "priority": item["priority"],
            },
        }
        for item in selected
    ]
    summary_names = ", ".join(skill["name"] for skill in selected_skills[:3])
    context_summary_text = f"Recommended skills for query `{query}` on host `{host}`: {summary_names}"
    return {
        "selected_skills": selected_skills,
        "excluded_summary": [
            {
                "id": item["skill"].name,
                "reason": "not_selected",
            }
            for item in ranked
            if item not in selected
        ],
        "context_summary_text": context_summary_text,
    }


def _query_terms(query: str) -> list[str]:
    words = [part.strip(".,:()[]`").lower() for part in query.split()]
    return [word for word in words if len(word) > 2]


def _truncate_preview(preview: str, limit: int = 220) -> str:
    if len(preview) <= limit:
        return preview
    return preview[: limit - 3].rstrip() + "..."


def _priority_for_skill(skill: Skill, lowered: str) -> int:
    priority = 5
    if skill.source == "project":
        priority += 2
    if "recommended" in lowered or "best" in lowered:
        priority += 1
    if "skill" in lowered and "select" in lowered:
        priority += 1
    return priority
