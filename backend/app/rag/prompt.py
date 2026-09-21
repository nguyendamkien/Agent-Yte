"""Prompt construction for grounded medical answers."""

from typing import Any


def build_context(results: list[dict[str, Any]]) -> str:
	if not results:
		return "Không tìm thấy tài liệu phù hợp trong cơ sở dữ liệu."
	blocks = []
	for index, result in enumerate(results, start=1):
		metadata = result.get("metadata", {})
		blocks.append(
			f"[Nguồn {index}] {metadata.get('title', '')} | "
			f"Mục: {metadata.get('section', '')}\n"
			f"Nội dung: {result.get('text', '')}\n"
			f"URL: {metadata.get('url', '')}"
		)
	return "\n\n".join(blocks)


def build_rag_prompt(question: str, context: str) -> str:
	return f"""Dựa CHỈ trên CONTEXT dưới đây, hãy trả lời câu hỏi bằng tiếng Việt.

Quy tắc:
- Nếu context không đủ, nói rõ là chưa tìm thấy thông tin phù hợp; không tự bịa.
- Đây là thông tin tham khảo, không chẩn đoán cá nhân và không kê đơn/liều thuốc.
- Nếu có dấu hiệu cấp cứu, khuyên gọi 115 hoặc đến cơ sở y tế gần nhất.
- Trả lời ngắn gọn, dễ hiểu và nêu nguồn khi sử dụng thông tin.

CONTEXT:
{context}

CÂU HỎI:
{question}
"""