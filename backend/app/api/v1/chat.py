"""Chat API routes backed by ChatServiceV3."""

import json
import threading
from typing import Any, AsyncIterator, Dict, List, Optional

from fastapi import APIRouter, Header, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse

from app.schemas import ChatMessage, ChatRequest, ChatResponse
from app.services.auth_service import AuthError, auth_service
from app.services.chat_service_v3 import chat_service_v3 as chat_service

router = APIRouter()

_MAX_SESSION_ID_LEN = 128
_MAX_MESSAGE_LEN = 4096


class ConnectionManager:
    """Thread-safe WebSocket connection manager."""

    def __init__(self):
        self._lock = threading.Lock()
        self.active_connections: dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, session_id: str):
        await websocket.accept()
        with self._lock:
            self.active_connections[session_id] = websocket

    def disconnect(self, session_id: str):
        with self._lock:
            self.active_connections.pop(session_id, None)

    async def send_message(self, session_id: str, message: dict):
        with self._lock:
            websocket = self.active_connections.get(session_id)
        if websocket is not None:
            await websocket.send_json(message)


manager = ConnectionManager()


def _normalize_user_id(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    value = value.strip()
    return value or None


def _resolve_authenticated_user_id(
    authorization: Optional[str],
    requested_user_id: Optional[str] = None,
) -> str:
    try:
        user = auth_service.get_user_from_authorization(authorization)
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    user_id = _normalize_user_id(user.get("id"))
    if not user_id:
        raise HTTPException(status_code=401, detail="invalid token user")

    req_uid = _normalize_user_id(requested_user_id)
    if req_uid and req_uid != user_id:
        raise HTTPException(status_code=403, detail="token user_id mismatch")

    return user_id


def _resolve_ws_user_id(
    websocket: WebSocket,
    message_token: Optional[str] = None,
    requested_user_id: Optional[str] = None,
) -> str:
    raw_auth = websocket.headers.get("authorization")
    raw_query_token = websocket.query_params.get("token")

    if raw_query_token:
        raw_auth = f"Bearer {raw_query_token}"

    if message_token:
        raw_auth = f"Bearer {message_token}"

    return _resolve_authenticated_user_id(raw_auth, requested_user_id=requested_user_id)


async def _iter_stream_chunks(
    session_id: str,
    user_id: str,
    message: str,
    history: Optional[List[Dict[str, Any]]] = None,
) -> AsyncIterator[Dict[str, Any]]:
    """Unified streaming adapter for SSE and WebSocket."""
    history = history or []

    if hasattr(chat_service, "stream_process_message"):
        async for chunk in chat_service.stream_process_message(
            session_id=session_id,
            user_id=user_id,
            message=message,
            history=history,
        ):
            if isinstance(chunk, dict):
                yield chunk
        return

    result = await chat_service.process_message(
        session_id=session_id,
        user_id=user_id,
        message=message,
        history=history,
    )
    yield {"content": result.get("message", ""), "done": False}
    yield {"content": "", "done": True}


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, authorization: Optional[str] = Header(default=None)):
    if not request.session_id or len(request.session_id) > _MAX_SESSION_ID_LEN:
        raise HTTPException(status_code=400, detail="session_id invalid")

    if not request.message or len(request.message) > _MAX_MESSAGE_LEN:
        raise HTTPException(status_code=400, detail="message invalid")

    user_id = _resolve_authenticated_user_id(authorization, requested_user_id=request.user_id)

    try:
        history_dict = [h.model_dump() for h in request.history] if request.history else []
        result = await chat_service.process_message(
            session_id=request.session_id,
            user_id=user_id,
            message=request.message,
            history=history_dict,
        )
        return ChatResponse(**result)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"process failed: {str(exc)}") from exc


@router.post("/chat/stream")
async def stream_chat(request: ChatRequest, authorization: Optional[str] = Header(default=None)):
    if not request.session_id or len(request.session_id) > _MAX_SESSION_ID_LEN:
        raise HTTPException(status_code=400, detail="session_id invalid")

    if not request.message or len(request.message) > _MAX_MESSAGE_LEN:
        raise HTTPException(status_code=400, detail="message invalid")

    user_id = _resolve_authenticated_user_id(authorization, requested_user_id=request.user_id)

    async def generate():
        try:
            history_dict = [h.model_dump() for h in request.history] if request.history else []
            done_sent = False

            async for chunk in _iter_stream_chunks(
                session_id=request.session_id,
                user_id=user_id,
                message=request.message,
                history=history_dict,
            ):
                done_sent = done_sent or bool(chunk.get("done", False))
                yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"

            if not done_sent:
                yield f"data: {json.dumps({'content': '', 'done': True}, ensure_ascii=False)}\n\n"
        except PermissionError as exc:
            err = {"error": str(exc), "done": True, "status": 403}
            yield f"data: {json.dumps(err, ensure_ascii=False)}\n\n"
        except ValueError as exc:
            err = {"error": str(exc), "done": True, "status": 400}
            yield f"data: {json.dumps(err, ensure_ascii=False)}\n\n"
        except Exception as exc:
            err = {"error": str(exc), "done": True, "status": 500}
            yield f"data: {json.dumps(err, ensure_ascii=False)}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.get("/chat/history/{session_id}")
async def get_history(
    session_id: str,
    authorization: Optional[str] = Header(default=None),
    user_id: Optional[str] = Query(default=None),
):
    if not session_id or len(session_id) > _MAX_SESSION_ID_LEN:
        raise HTTPException(status_code=400, detail="session_id invalid")

    auth_user_id = _resolve_authenticated_user_id(authorization, requested_user_id=user_id)

    try:
        history = chat_service.get_session_history(session_id, user_id=auth_user_id)
        messages = [ChatMessage(role=msg["role"], content=msg["content"]) for msg in history]
        return {"session_id": session_id, "messages": messages, "count": len(messages)}
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"history fetch failed: {str(exc)}") from exc


@router.delete("/chat/history/{session_id}")
async def clear_history(
    session_id: str,
    authorization: Optional[str] = Header(default=None),
    user_id: Optional[str] = Query(default=None),
):
    if not session_id or len(session_id) > _MAX_SESSION_ID_LEN:
        raise HTTPException(status_code=400, detail="session_id invalid")

    auth_user_id = _resolve_authenticated_user_id(authorization, requested_user_id=user_id)

    try:
        success = chat_service.clear_session(session_id, user_id=auth_user_id)
        if success:
            return {"message": "history cleared", "session_id": session_id}
        return {"message": "session not found", "session_id": session_id}
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"history clear failed: {str(exc)}") from exc


@router.websocket("/chat/ws/{session_id}")
async def websocket_chat(websocket: WebSocket, session_id: str):
    if not session_id or len(session_id) > _MAX_SESSION_ID_LEN:
        await websocket.close(code=4000, reason="session_id invalid")
        return

    await manager.connect(websocket, session_id)

    try:
        greeting_message = (
            chat_service.greeting_message
            if hasattr(chat_service, "greeting_message")
            else "Hello, how can I help you?"
        )
        await manager.send_message(
            session_id,
            {"type": "greeting", "content": greeting_message, "is_greeting": True},
        )

        connection_user_id: Optional[str] = None

        while True:
            try:
                data = await websocket.receive_text()
            except WebSocketDisconnect:
                break

            try:
                message_data = json.loads(data)
            except json.JSONDecodeError:
                await manager.send_message(session_id, {"type": "error", "content": "invalid JSON"})
                continue

            message = (message_data.get("message") or "").strip()
            history = message_data.get("history", [])
            message_user_id = _normalize_user_id(message_data.get("user_id"))
            message_token = (message_data.get("token") or "").strip() or None

            try:
                resolved_user_id = _resolve_ws_user_id(
                    websocket,
                    message_token=message_token,
                    requested_user_id=message_user_id,
                )
            except HTTPException as exc:
                await manager.send_message(session_id, {"type": "error", "content": str(exc.detail)})
                continue

            if connection_user_id and resolved_user_id != connection_user_id:
                await manager.send_message(session_id, {"type": "error", "content": "user_id mismatch"})
                continue
            connection_user_id = resolved_user_id

            if not message or len(message) > _MAX_MESSAGE_LEN:
                await manager.send_message(session_id, {"type": "error", "content": "message invalid"})
                continue

            await manager.send_message(session_id, {"type": "status", "content": "thinking..."})

            try:
                async for chunk in _iter_stream_chunks(
                    session_id=session_id,
                    user_id=connection_user_id,
                    message=message,
                    history=history,
                ):
                    await manager.send_message(
                        session_id,
                        {
                            "type": "chunk",
                            "content": chunk.get("content", ""),
                            "done": chunk.get("done", False),
                            "meta": chunk.get("meta"),
                        },
                    )
                await manager.send_message(session_id, {"type": "done", "content": ""})
            except PermissionError as exc:
                await manager.send_message(session_id, {"type": "error", "content": str(exc)})
            except Exception as exc:
                await manager.send_message(session_id, {"type": "error", "content": f"process failed: {str(exc)}"})

    except Exception as exc:
        await manager.send_message(session_id, {"type": "error", "content": f"process failed: {str(exc)}"})
    finally:
        manager.disconnect(session_id)
