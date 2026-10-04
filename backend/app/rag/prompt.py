"""Prompt construction for grounded medical answers."""

from typing import Any


def source_key(metadata: dict[str, Any]) -> str:
	"""Khoá nhận diện một bài viết — các chunk cùng bài dùng chung một số [Nguồn i]."""
	return metadata.get("url") or metadata.get("document_id", "")


def build_context(results: list[dict[str, Any]]) -> str:
	"""Đánh số nguồn theo bài (thứ tự xuất hiện đầu tiên), không theo chunk, để
	"[Nguồn i]" trong câu trả lời khớp với nguồn thứ i trong danh sách trả về frontend."""
	if not results:
		return "Không tìm thấy tài liệu phù hợp trong cơ sở dữ liệu."
	numbers: dict[str, int] = {}
	blocks = []
	for result in results:
		metadata = result.get("metadata", {})
		index = numbers.setdefault(source_key(metadata), len(numbers) + 1)
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