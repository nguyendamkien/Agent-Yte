from fastapi import APIRouter, HTTPException

from app.schemas import ChatRequest, ChatResponse
from app.services.rag_service import get_rag_service

router = APIRouter(prefix="/api", tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    try:
        service = get_rag_service()
        reply, sources = service.ask(request.message, request.history)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:  # lỗi gọi Gemini API (mạng, quota, key sai...)
        raise HTTPException(
            status_code=502, detail=f"Không thể lấy phản hồi từ Gemini: {exc}"
        ) from exc

    return ChatResponse(reply=reply, sources=sources)
