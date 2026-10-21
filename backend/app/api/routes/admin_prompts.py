"""Administrator-only release status/refresh. Never returns prompt bodies or keys."""
from fastapi import APIRouter, Depends
from app.core.auth import get_current_admin
from app.core.config import get_settings
from app.core.prompt_service import get_release_manager

router=APIRouter(prefix="/admin/prompts",tags=["admin-prompts"])

@router.get("")
async def status(admin:str=Depends(get_current_admin)):
    s=get_settings()
    return {**get_release_manager().status(),"remote_enabled":s.prompt_remote_enabled,
            "channel":s.prompt_remote_channel,"ab_enabled":s.prompt_ab_enabled and s.prompt_ab_live_approved,
            "explicit_cache_enabled":s.gemini_explicit_cache_enabled,"private_cache_enabled":s.gemini_private_cache_enabled}

@router.post("/refresh")
async def refresh(admin:str=Depends(get_current_admin)):
    if get_settings().prompt_remote_enabled:await get_release_manager().refresh(force=True)
    return await status(admin)
