"""
健康检查 API
"""
from fastapi import APIRouter
from datetime import datetime

from app.schemas import HealthResponse
from app.config import settings

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """健康检查"""
    return HealthResponse(
        status="healthy",
        version=settings.app_version,
        timestamp=datetime.now()
    )
