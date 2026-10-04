"""End-to-end RAG evaluation with an LLM judge — 4 tiêu chí RAGAS.

Chạy từng câu trong golden set qua pipeline thật (retrieve → Gemini), rồi dùng một
model OpenAI khác họ với generator làm giám khảo chấm 4 tiêu chí:

  Retrieval   context_precision   chunk liên quan có được xếp trên cùng không
              context_recall      context có đủ thông tin (key_facts) để trả lời không
  Generation  faithfulness        câu trả lời có bịa ngoài context không
              answer_relevancy    câu trả lời có đúng trọng tâm câu hỏi không

Run from backend/:  python -m eval.eval_rag [--limit 10] [--ids gout-01,hbv-02] [--judge-model gpt-4.1-mini]
"""

import argparse
import json
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from app.config import get_settings
from app.rag.embeddings import _get_client
from app.schemas import ChatMessage
from app.services.rag_service import get_rag_service
from eval.eval_retrieval import load_golden

DEFAULT_JUDGE_MODEL = "gpt-4.1-mini"
DEFAULT_OUT = Path(__file__).parent / "results_rag.json"

JUDGE_PROMPT = """Bạn là giám khảo đánh giá hệ thống RAG hỏi đáp y tế tiếng Việt. Chấm khách quan, chặt chẽ.

# CÂU HỎI
{question}

# LỊCH SỬ HỘI THOẠI (nếu có)
{history}

# CONTEXT hệ thống đã truy xuất (đánh số)
{contexts}

# CÂU TRẢ LỜI của hệ thống
{answer}

# KEY FACTS — các ý cần có để trả lời đúng (đánh số)
{key_facts}

Trả về JSON đúng schema sau, không thêm gì khác:
{{
  "context_relevance": [<0|1 cho từng context theo thứ tự: 1 nếu context đó chứa thông tin hữu ích để trả lời câu hỏi>],
  "context_recall": [<0|1 cho từng key fact: 1 nếu key fact đó có thể suy ra từ CONTEXT>],
  "claims": [{{"claim": "<một khẳng định y khoa/thông tin cụ thể trong câu trả lời>", "supported": <true|false: được CONTEXT hỗ trợ>}}],
  "answer_relevancy": <1-5: câu trả lời giải quyết đúng câu hỏi đến mức nào (5 = trực tiếp, đầy đủ, không lan man)>,
  "notes": "<tối đa 1 câu: lỗi chính nếu có>"
}}

Lưu ý:
- "claims": chỉ liệt kê khẳng định mang tính thông tin y khoa (triệu chứng, con số, thuốc, nguyên nhân...). BỎ QUA: lời khuyên chung ("nên đi khám bác sĩ", "thông tin chỉ tham khảo", "gọi 115"), câu nói về việc thiếu dữ liệu ("không tìm thấy thông tin về X"), và lời cảnh báo chung rằng triệu chứng là nguy hiểm/cần cấp cứu. Nếu không còn claim nào thì trả về mảng rỗng.
- Một claim được hỗ trợ khi CONTEXT nêu rõ hoặc suy ra trực tiếp được; kiến thức đúng nhưng không có trong CONTEXT vẫn là false.
- Nếu không có key fact thì "context_recall" là mảng rỗng.
- Độ dài các mảng phải khớp đúng số context / số key fact."""

METRICS = ["context_precision", "context_recall", "faithfulness", "answer_relevancy"]


def with_retry(fn, *args, attempts: int = 5, **kwargs):
	for attempt in range(attempts):
		try:
			return fn(*args, **kwargs)
		except Exception:  # rate limit, lỗi mạng...
			if attempt == attempts - 1:
				raise
			time.sleep(2 ** (attempt + 1))


def judge(item: dict, answer: str, results: list[dict], model: str) -> dict:
	contexts = "\n\n".join(
		f"[{i}] ({r['metadata'].get('title', '')} | {r['metadata'].get('section', '')})\n{r['text']}"
		for i, r in enumerate(results, start=1)
	) or "(không có context)"
	history = "\n".join(f"{m['role']}: {m['content']}" for m in item["history"]) or "(không có)"
	key_facts = "\n".join(f"{i}. {fact}" for i, fact in enumerate(item["key_facts"], start=1)) or "(không có)"
	prompt = JUDGE_PROMPT.format(
		question=item["question"], history=history, contexts=contexts, answer=answer, key_facts=key_facts
	)
	response = _get_client().chat.completions.create(
		model=model,
		messages=[{"role": "user", "content": prompt}],
		response_format={"type": "json_object"},
		temperature=0,
	)
	return json.loads(response.choices[0].message.content)


def average_precision(relevance: list[int]) -> float | None:
	"""Context precision kiểu RAGAS: trung bình precision@k tại các vị trí có chunk liên quan,
	nên chunk liên quan xếp càng cao thì điểm càng cao."""
	if not any(relevance):
		return 0.0 if relevance else None
	hits, total = 0, 0.0
	for k, rel in enumerate(relevance, start=1):
		if rel:
			hits += 1
			total += hits / k
	return total / hits


def mean(values: list) -> float | None:
	values = [v for v in values if v is not None]
	return sum(values) / len(values) if values else None


def score_item(item: dict, answer: str, results: list[dict], verdict: dict) -> dict:
	n_ctx, n_facts = len(results), len(item["key_facts"])
	relevance = [int(bool(x)) for x in verdict.get("context_relevance", [])][:n_ctx]
	claims = verdict.get("claims", [])
	# Context metrics chỉ có nghĩa khi dữ liệu thực sự có bài trả lời được câu hỏi.
	has_gold_docs = bool(item["relevant_doc_ids"])

	return {
		"id": item["id"],
		"type": item["type"],
		"question": item["question"],
		"answer": answer,
		"retrieved": [
			{"doc": r["metadata"].get("document_id"), "section": r["metadata"].get("section"), "score": round(r["score"], 3)}
			for r in results
		],
		"context_precision": average_precision(relevance) if has_gold_docs else None,
		"context_recall": mean(verdict.get("context_recall", [])[:n_facts]) if has_gold_docs else None,
		"faithfulness": sum(bool(c.get("supported")) for c in claims) / len(claims) if claims else None,
		# Câu ngoài phạm vi / an toàn mong đợi từ chối, nên không chấm độ đúng trọng tâm.
		"answer_relevancy": (verdict.get("answer_relevancy", 1) - 1) / 4 if item["expected_behavior"] == "answer" else None,
		"unsupported_claims": [c.get("claim") for c in claims if not c.get("supported")],
		"notes": verdict.get("notes", ""),
	}


def run_item(item: dict, judge_model: str) -> dict:
	history = [ChatMessage(**m) for m in item["history"]]
	started = time.perf_counter()
	try:
		answer, _, results = with_retry(get_rag_service().ask_with_context, item["question"], history)
	except Exception as exc:
		return {"id": item["id"], "type": item["type"], "question": item["question"], "error": f"generation: {exc}"}
	latency = time.perf_counter() - started
	try:
		verdict = with_retry(judge, item, answer, results, judge_model)
	except Exception as exc:
		return {"id": item["id"], "type": item["type"], "question": item["question"], "answer": answer, "error": f"judge: {exc}"}
	row = score_item(item, answer, results, verdict)
	row["latency_s"] = round(latency, 2)
	return row


def fmt(value: float | None) -> str:
	return "—" if value is None else f"{value:.2f}"


def print_summary(rows: list[dict]) -> None:
	groups: dict[str, list[dict]] = defaultdict(list)
	for row in rows:
		groups[row["type"]].append(row)
	print("  " + "group".ljust(16) + "n".rjust(4) + "".join(m.rjust(20) for m in METRICS))
	for name, members in [("ALL", rows), *sorted(groups.items())]:
		cells = "".join(fmt(mean([r.get(m) for r in members])).rjust(20) for m in METRICS)
		print("  " + name.ljust(16) + str(len(members)).rjust(4) + cells)


def main() -> None:
	parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
	parser.add_argument("--judge-model", default=DEFAULT_JUDGE_MODEL)
	parser.add_argument("--limit", type=int, default=None, help="Chỉ chạy N câu đầu (thử nhanh)")
	parser.add_argument("--ids", default=None, help="Danh sách id, cách nhau bởi dấu phẩy")
	parser.add_argument("--workers", type=int, default=3, help="Số câu chạy song song (giữ thấp để tránh rate limit Gemini)")
	parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
	args = parser.parse_args()

	settings = get_settings()
	golden = load_golden()
	if args.ids:
		wanted = set(args.ids.split(","))
		golden = [item for item in golden if item["id"] in wanted]
	if args.limit:
		golden = golden[: args.limit]

	rerank = f" + rerank({settings.rerank_candidates} ứng viên)" if settings.rerank_enabled else ""
	print(f"Đánh giá {len(golden)} câu | generator={settings.gemini_model} | judge={args.judge_model} | "
		  f"retrieval={settings.retrieval_mode}{rerank} | top_k={settings.rag_top_k}")
	get_rag_service()  # khởi tạo một lần trước khi chạy song song

	rows: list[dict] = []
	with ThreadPoolExecutor(max_workers=args.workers) as pool:
		for done, row in enumerate(pool.map(lambda item: run_item(item, args.judge_model), golden), start=1):
			rows.append(row)
			status = f"LỖI {row['error']}" if "error" in row else " ".join(f"{m.split('_')[-1]}={fmt(row[m])}" for m in METRICS)
			print(f"  [{done}/{len(golden)}] {row['id']:<12} {status}")

	scored = [r for r in rows if "error" not in r]
	errors = [r for r in rows if "error" in r]
	print("\n== Kết quả 4 tiêu chí RAGAS (0–1, cao hơn là tốt hơn)")
	print_summary(scored)

	print("\n== Cần xem lại")
	for row in scored:
		problems = [
			f"{m}={row[m]:.2f}"
			for m, threshold in (("faithfulness", 1.0), ("context_recall", 0.5), ("answer_relevancy", 0.5))
			if row[m] is not None and row[m] < threshold
		]
		if problems:
			print(f"  {row['id']:<12} {', '.join(problems)} — {row['notes']}")
	for row in errors:
		print(f"  {row['id']:<12} {row['error']}")

	args.out.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
	print(f"\nChi tiết từng câu (câu trả lời, claim không được hỗ trợ...): {args.out}")


if __name__ == "__main__":
	main()
