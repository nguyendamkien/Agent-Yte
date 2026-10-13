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
- Đây là thông tin tham khảo, không chẩn đoán cá nhân và không kê đơn.
- KHÔNG nêu liều dùng của bất kỳ thuốc nào: không hàm lượng (mg, g, ml, viên…), số lần \
mỗi ngày, hay thời gian dùng thuốc — KỂ CẢ khi CONTEXT có ghi, kể cả gọi là "liều tham \
khảo" hay đặt trong ngoặc. Được nêu tên thuốc / nhóm thuốc và lưu ý chung; liều dùng \
phải do bác sĩ chỉ định.
- Nếu có dấu hiệu cấp cứu, khuyên gọi 115 hoặc đến cơ sở y tế gần nhất.
- Trả lời ngắn gọn, dễ hiểu và nêu nguồn khi sử dụng thông tin.

CONTEXT:
{context}

CÂU HỎI:
{question}
"""


def build_no_context_prompt(question: str) -> str:
	"""Prompt khi retrieve không ra chunk nào. Tách riêng khỏi build_rag_prompt vì với
	prompt chung, Gemini vẫn nói "chưa tìm thấy" nhưng kể thêm triệu chứng / yếu tố tiên
	lượng lấy từ kiến thức của nó — thông tin không có nguồn."""
	return f"""Cơ sở dữ liệu KHÔNG có tài liệu nào liên quan đến câu hỏi dưới đây.

Hãy trả lời bằng tiếng Việt, tối đa 3 câu:
- Nếu câu hỏi không thuộc lĩnh vực sức khỏe: lịch sự cho biết bạn chỉ hỗ trợ các vấn đề \
liên quan đến sức khỏe.
- Nếu câu hỏi về sức khỏe: nói rõ hiện chưa có thông tin về chủ đề này trong dữ liệu, \
khuyên hỏi bác sĩ hoặc đến cơ sở y tế; nếu câu hỏi gợi ý tình trạng khẩn cấp, khuyên \
gọi 115 hoặc đến cơ sở y tế gần nhất ngay.
- KHÔNG nêu bất kỳ triệu chứng, nguyên nhân, con số, thuốc, phương pháp điều trị hay \
yếu tố tiên lượng nào — kể cả để làm ví dụ hoặc đặt trong ngoặc.

CÂU HỎI:
{question}
"""


def build_prompt(question: str, results: list[dict[str, Any]]) -> str:
	if not results:
		return build_no_context_prompt(question)
	return build_rag_prompt(question, build_context(results))