"""Skills management API."""

from fastapi import APIRouter, HTTPException

from app.schemas import SkillsListResponse, SkillInfo
from skills.manager import skill_manager

router = APIRouter()


@router.get("/skills", response_model=SkillsListResponse)
async def list_skills():
    """List all registered skills."""
    skills_info = []
    for skill_name in skill_manager.list_skills():
        skill = skill_manager.get(skill_name)
        if not skill:
            continue
        skills_info.append(
            SkillInfo(
                name=skill.name,
                description=skill.description,
                skill_type=skill.skill_type.value,
                enabled=bool(getattr(skill.config, "enabled", True)),
            )
        )

    return SkillsListResponse(skills=skills_info, count=len(skills_info))


@router.get("/skills/stats")
async def get_stats():
    """Get skill execution statistics."""
    return skill_manager.get_statistics()


@router.get("/skills/{skill_name}")
async def get_skill(skill_name: str):
    """Get one skill detail."""
    skill = skill_manager.get(skill_name)
    if not skill:
        raise HTTPException(status_code=404, detail=f"skill '{skill_name}' not found")

    return {
        "name": skill.name,
        "description": skill.description,
        "skill_type": skill.skill_type.value,
        "enabled": bool(getattr(skill.config, "enabled", True)),
        "prompt": skill.get_prompt(),
    }
