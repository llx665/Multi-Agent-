"""
评测 API 端点
提供 Agent 输出评测相关接口
"""
from fastapi import APIRouter, HTTPException
from typing import Dict, Any

from app.schemas import EvaluationRequest, EvaluationResponse, EvaluationReportResponse

router = APIRouter()


@router.post("/evaluation/response", response_model=Dict[str, Any])
async def evaluate_response(request: EvaluationRequest):
    """
    评测单次 Agent 回复

    对 Agent 的输出进行多维度质量评测，包括：
    - Relevance（相关性）
    - Accuracy（准确性）
    - Completeness（完整性）
    - Helpfulness（有用性）
    - RAG Recall（RAG 召回率）
    - Sensitive Info Leak（敏感信息泄露）
    - Hallucination Rate（幻觉率）
    """
    try:
        from app.services.evaluation_service import evaluation_service

        result = evaluation_service.evaluate_response(
            session_id=request.session_id,
            query=request.query,
            response=request.response,
            context=request.context
        )

        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/evaluation/report/{session_id}", response_model=Dict[str, Any])
async def get_session_evaluation_report(session_id: str):
    """
    获取会话评测报告

    Returns:
        会话统计信息和评测结果
    """
    try:
        from app.services.evaluation_service import evaluation_service

        report = evaluation_service.get_session_report(session_id)

        if not report:
            raise HTTPException(status_code=404, detail=f"会话 {session_id} 不存在")

        return report

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/evaluation/stats/global", response_model=Dict[str, Any])
async def get_global_evaluation_stats():
    """
    获取全局评测统计

    Returns:
        跨会话聚合统计
    """
    try:
        from app.services.evaluation_service import evaluation_service

        return evaluation_service.get_global_stats()

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/evaluation/export/{session_id}")
async def export_session_evaluation(session_id: str):
    """
    导出会话评测报告为 Markdown

    Returns:
        Markdown 格式的完整报告
    """
    try:
        from app.services.evaluation_service import evaluation_service

        content = evaluation_service.export_session_markdown(session_id)

        if "不存在" in content:
            raise HTTPException(status_code=404, detail=content)

        return {
            "session_id": session_id,
            "content": content,
            "format": "markdown"
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
