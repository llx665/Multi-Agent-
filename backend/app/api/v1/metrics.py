"""
指标监控 API 端点
提供 Prometheus 格式的指标和统计信息

统一错误处理：
- 所有端点都有 try-catch
- 错误时返回 500 状态码和错误信息
"""

from fastapi import APIRouter, Response, HTTPException

router = APIRouter()


@router.get("/metrics")
async def get_metrics():
    """
    获取 Prometheus 格式的指标

    Returns:
        Prometheus 格式的文本指标
    """
    try:
        from monitoring.metrics import metrics_collector

        metrics_text = metrics_collector.export_prometheus_format()

        return Response(
            content=metrics_text,
            media_type="text/plain"
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"获取指标失败: {str(e)}")


@router.get("/metrics/summary")
async def get_metrics_summary():
    """
    获取人类可读的指标摘要

    Returns:
        指标摘要信息
    """
    try:
        from monitoring.metrics import metrics_collector

        return {
            "summary": metrics_collector.get_summary(),
            "stats": metrics_collector._get_stats()
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"获取指标摘要失败: {str(e)}")


@router.post("/metrics/reset")
async def reset_metrics():
    """
    重置指标统计

    Returns:
        重置结果
    """
    try:
        from monitoring.metrics import metrics_collector

        metrics_collector.reset()
        return {"message": "指标已重置"}
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"重置指标失败: {str(e)}")


@router.get("/health/detailed")
async def get_detailed_health():
    """
    获取详细健康状态

    Returns:
        详细健康信息
    """
    try:
        from monitoring.metrics import metrics_collector

        stats = metrics_collector._get_stats()

        # 判断健康状态
        error_rate = stats.get("errors", {}).get("rate", 0)
        avg_latency = stats.get("latency_ms", {}).get("avg", 0)

        if error_rate > 0.1:  # 错误率超过10%
            status = "degraded"
            reason = f"错误率过高: {error_rate:.2%}"
        elif avg_latency > 5000:  # 平均延迟超过5秒
            status = "degraded"
            reason = f"延迟过高: {avg_latency:.2f}ms"
        else:
            status = "healthy"
            reason = "所有指标正常"

        return {
            "status": status,
            "reason": reason,
            "timestamp": stats.get("timestamp", ""),
            "requests_total": stats.get("requests", {}).get("total", 0),
            "error_rate": error_rate,
            "avg_latency_ms": avg_latency,
            "active_sessions": stats.get("sessions", {}).get("active", 0)
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"获取健康状态失败: {str(e)}")
