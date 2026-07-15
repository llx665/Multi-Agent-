"""Pydantic schema definitions."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: str = Field(..., description="message role: user/assistant/system")
    content: str = Field(..., description="message content")
    timestamp: Optional[datetime] = None


class ChatRequest(BaseModel):
    session_id: str = Field(..., description="session id")
    user_id: Optional[str] = Field(default=None, description="user id for session authorization")
    message: str = Field(..., description="user message")
    history: Optional[List[ChatMessage]] = Field(default_factory=list, description="chat history")


class ChatResponse(BaseModel):
    session_id: str
    trace_id: Optional[str] = None
    message: str
    customer_type: Optional[str] = None
    skills_used: List[str] = Field(default_factory=list)
    sources: List[str] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=datetime.now)
    intent: Optional[str] = None
    evaluation_score: Optional[float] = None
    retrieved_documents: List[Dict[str, Any]] = Field(default_factory=list)
    retrieved_count: int = 0
    has_relevant_info: bool = False
    rag_fallback: Optional[Dict[str, Any]] = None
    context_summary: Optional[Dict[str, Any]] = None
    fusion_info: Optional[Dict[str, Any]] = Field(default=None, description="context+rAG fusion info")
    greeting: Optional[str] = Field(default=None, description="new-session greeting")


class SkillInfo(BaseModel):
    name: str
    description: str
    skill_type: str
    enabled: bool


class SkillsListResponse(BaseModel):
    skills: List[SkillInfo]
    count: int


class HistoryResponse(BaseModel):
    session_id: str
    messages: List[ChatMessage]
    count: int


class HealthResponse(BaseModel):
    status: str
    version: str
    timestamp: datetime


class EvaluationRequest(BaseModel):
    session_id: str = Field(..., description="session id")
    query: str = Field(..., description="user query")
    response: str = Field(..., description="agent response")
    context: Optional[Dict[str, Any]] = Field(default_factory=dict, description="context data")


class MetricResultSchema(BaseModel):
    metric_type: str
    value: float
    details: str = ""
    threshold: Optional[float] = None
    passed: bool = True


class EvaluationResponse(BaseModel):
    session_id: str
    timestamp: str
    query: str
    response: str
    metrics: Dict[str, MetricResultSchema]
    overall_score: float
    grade: str
    skill_results: List[Dict] = Field(default_factory=list)
    tool_usage: List[str] = Field(default_factory=list)


class EvaluationReportResponse(BaseModel):
    session_id: str
    statistics: Dict[str, Any]
    global_stats: Dict[str, Any]
