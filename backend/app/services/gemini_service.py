""" dịch vụ Gemini: giao tiếp với mô hình ngôn ngữ Gemini để trả lời câu hỏi y tế """
from collections.abc import Iterator

import google.generativeai as genai

from app.config import get_settings
from app.schemas import ChatMessage

SYSTEM_INSTRUCTION = """\
Bạn là một trợ lý ảo hỗ trợ tư vấn thông tin y tế bằng tiếng Việt.

Nguyên tắc trả lời:
- Trả lời rõ ràng, dễ hiểu, đúng trọng tâm câu hỏi.
- Chỉ cung cấp thông tin y tế mang tính tham khảo chung (triệu chứng, nguyên \
nhân phổ biến, cách chăm sóc/phòng ngừa cơ bản...).
- KHÔNG chẩn đoán bệnh cụ thể cho từng cá nhân, KHÔNG kê đơn thuốc hay liều \
lượng cụ thể.
- Nếu câu hỏi liên quan đến triệu chứng nghiêm trọng, cấp cứu (đau ngực dữ \
dội, khó thở, chảy máu nhiều, mất ý thức...), khuyến cáo người dùng đến ngay \
cơ sở y tế gần nhất hoặc gọi cấp cứu 115.
- Luôn nhắc người dùng nên đi khám bác sĩ hoặc chuyên gia y tế để được chẩn \
đoán và điều trị chính xác.
- Nếu câu hỏi không thuộc lĩnh vực y tế, lịch sự cho biết bạn chỉ hỗ trợ các \
vấn đề liên quan đến sức khỏe.
"""


REWRITE_INSTRUCTION = """\
Bạn viết lại câu hỏi của người dùng trong một cuộc trò chuyện về sức khỏe thành \
MỘT câu hỏi độc lập, đủ ý, dùng để tìm kiếm tài liệu y tế.

Quy tắc:
- Thay các từ chỉ trỏ ("nó", "bệnh này", "vậy", "còn ... thì sao") bằng đúng tên \
bệnh / thuốc / thực phẩm được nhắc trong lịch sử.
- Giữ nguyên ý và phạm vi câu hỏi; KHÔNG trả lời, KHÔNG thêm thông tin mới.
- Nếu câu hỏi đã đủ ý hoặc không liên quan đến lịch sử, trả lại nguyên văn.
- Chỉ in ra câu hỏi đã viết lại, không giải thích, không đặt trong dấu ngoặc kép.
"""

# Câu trả lời cũ của bot có thể rất dài; chỉ cần phần đầu để biết đang nói về bệnh gì.
REWRITE_MAX_REPLY_CHARS = 500


class GeminiService:
    def __init__(self) -> None:
        settings = get_settings()
        if not settings.gemini_api_key:
            raise RuntimeError(
                "Thiếu GEMINI_API_KEY. Vui lòng tạo file .env từ .env.example "
                "và điền API key của bạn."
            )
        genai.configure(api_key=settings.gemini_api_key)
        self._model = genai.GenerativeModel(
            model_name=settings.gemini_model,
            system_instruction=SYSTEM_INSTRUCTION,
        )
        self._rewriter = genai.GenerativeModel(
            model_name=settings.gemini_model,
            system_instruction=REWRITE_INSTRUCTION,
            generation_config={"temperature": 0},
        )

    def ask(self, message: str, history: list[ChatMessage]) -> str:
        response = self._start_chat(history).send_message(message)
        return response.text

    def ask_stream(self, message: str, history: list[ChatMessage]) -> Iterator[str]:
        """Như ask(), nhưng trả từng đoạn text ngay khi Gemini sinh ra."""
        response = self._start_chat(history).send_message(message, stream=True)
        for chunk in response:
            # Chunk cuối có thể chỉ mang finish_reason, không có text.
            if chunk.parts and chunk.text:
                yield chunk.text

    def _start_chat(self, history: list[ChatMessage]):
        chat_history = [
            {"role": item.role, "parts": [item.content]} for item in history
        ]
        return self._model.start_chat(history=chat_history)

    def rewrite_query(self, message: str, history: list[ChatMessage]) -> str:
        """Viết lại câu hỏi nối tiếp thành câu độc lập dựa trên lịch sử (dùng để retrieve)."""
        lines = []
        for item in history:
            speaker = "Người dùng" if item.role == "user" else "Trợ lý"
            content = item.content
            if item.role == "model" and len(content) > REWRITE_MAX_REPLY_CHARS:
                content = content[:REWRITE_MAX_REPLY_CHARS] + "…"
            lines.append(f"{speaker}: {content}")
        prompt = (
            "LỊCH SỬ:\n" + "\n".join(lines)
            + f"\n\nCÂU HỎI MỚI: {message}\n\nCÂU HỎI VIẾT LẠI:"
        )
        return self._rewriter.generate_content(prompt).text


_service: GeminiService | None = None


def get_gemini_service() -> GeminiService:
    global _service
    if _service is None:
        _service = GeminiService()
    return _service
