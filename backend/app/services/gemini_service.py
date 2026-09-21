""" dịch vụ Gemini: giao tiếp với mô hình ngôn ngữ Gemini để trả lời câu hỏi y tế """
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

    def ask(self, message: str, history: list[ChatMessage]) -> str:
        chat_history = [
            {"role": item.role, "parts": [item.content]} for item in history
        ]
        chat = self._model.start_chat(history=chat_history)
        response = chat.send_message(message)
        return response.text


_service: GeminiService | None = None


def get_gemini_service() -> GeminiService:
    global _service
    if _service is None:
        _service = GeminiService()
    return _service
