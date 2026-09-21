from typing import Literal

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: Literal["user", "model"]
    content: str


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, description="Câu hỏi y tế của người dùng")
    history: list[ChatMessage] = Field(default_factory=list, description="Lịch sử hội thoại trước đó")


class Source(BaseModel):
    title: str
    url: str
    citation: str | None = None


class ChatResponse(BaseModel):
    reply: str
    sources: list[Source] = Field(default_factory=list)
    disclaimer: str = (
        "Thông tin trên chỉ mang tính tham khảo, không thay thế cho chẩn đoán "
        "và tư vấn của bác sĩ hoặc chuyên gia y tế."
    )
