"""Evaluate retrieval quality against the golden set.

Run from backend/:  python -m eval.eval_retrieval [--mode dense|hybrid] [--rerank] [--k 5] [--out eval/results.json]
                                       [--no-rewrite]
"""

import argparse
import json
from collections import defaultdict
from pathlib import Path

from app.config import get_settings
from app.rag.embeddings import embed_texts
from app.rag.loader import load_documents
from app.rag.retriever import Retriever
from app.rag.vector_store import ChromaVectorStore
from app.schemas import ChatMessage
from app.services.gemini_service import GeminiService
from app.services.rag_service import RagService, trim_history

GOLDEN_PATH = Path(__file__).parent / "golden_set.jsonl"


def load_golden() -> list[dict]:
	with GOLDEN_PATH.open(encoding="utf-8") as file:
		return [json.loads(line) for line in file if line.strip()]


def first_relevant_rank(results: list[dict], relevant: set[str]) -> int | None:
	for rank, result in enumerate(results, start=1):
		if result["metadata"].get("document_id") in relevant:
			return rank
	return None


def evaluate_item(item: dict, results: list[dict], disease_of: dict[str, str], dense_top1: float) -> dict:
	relevant = set(item["relevant_doc_ids"])
	rank = first_relevant_rank(results, relevant) if relevant else None
	retrieved_docs = [r["metadata"].get("document_id") for r in results]
	row = {
		"id": item["id"],
		"type": item["type"],
		"question": item["question"],
		# Cosine tốt nhất của nhánh dense — chính là điểm dùng cho ngưỡng RAG_MIN_SCORE.
		"top1_score": round(dense_top1, 3),
		"kept_after_threshold": len(results),
		"retrieved": [
			{"doc": r["metadata"].get("document_id"), "section": r["metadata"].get("section"), "score": round(r["score"], 3)}
			for r in results
		],
	}
	if relevant:
		row["rank"] = rank
		row["mrr"] = 1 / rank if rank else 0.0
		if item.get("expected_section"):
			row["section_hit"] = any(
				r["metadata"].get("document_id") in relevant and r["metadata"].get("section") == item["expected_section"]
				for r in results
			)
		if item.get("disease_group"):
			same = [disease_of.get(doc) == item["disease_group"] for doc in retrieved_docs]
			row["disease_precision"] = sum(same) / len(same) if same else 0.0
	return row


def summarize(rows: list[dict], k: int) -> dict:
	answerable = [r for r in rows if "rank" in r]
	summary = {"n": len(rows), "n_answerable": len(answerable)}
	if answerable:
		for cutoff in sorted({1, 3, k}):
			summary[f"hit@{cutoff}"] = sum(bool(r["rank"]) and r["rank"] <= cutoff for r in answerable) / len(answerable)
		summary["mrr"] = sum(r["mrr"] for r in answerable) / len(answerable)
		with_section = [r for r in answerable if "section_hit" in r]
		if with_section:
			summary["section_hit"] = sum(r["section_hit"] for r in with_section) / len(with_section)
		with_disease = [r for r in answerable if "disease_precision" in r]
		if with_disease:
			summary["disease_precision"] = sum(r["disease_precision"] for r in with_disease) / len(with_disease)
	return summary


def print_table(title: str, summaries: dict[str, dict]) -> None:
	keys = [key for key in ("n", "hit@1", "hit@3", "hit@5", "mrr", "section_hit", "disease_precision")
			if any(key in s for s in summaries.values())]
	print(f"\n== {title}")
	print("  " + "group".ljust(16) + "".join(key.rjust(18) for key in keys))
	for group, summary in summaries.items():
		cells = []
		for key in keys:
			value = summary.get(key, "")
			cells.append((f"{value:.2f}" if isinstance(value, float) else str(value)).rjust(18))
		print("  " + group.ljust(16) + "".join(cells))


def main() -> None:
	parser = argparse.ArgumentParser(description=__doc__)
	parser.add_argument("--k", type=int, default=None, help="Số chunk lấy về (mặc định RAG_TOP_K)")
	parser.add_argument("--mode", choices=["dense", "hybrid"], default=None, help="Mặc định RETRIEVAL_MODE")
	parser.add_argument("--rerank", action="store_true", help="Bật cross-encoder rerank (ONNX)")
	parser.add_argument("--out", type=Path, default=None, help="Ghi kết quả từng câu ra file JSON")
	parser.add_argument("--no-rewrite", action="store_true",
						help="Bỏ đo follow-up viết lại bằng Gemini (không cần GEMINI_API_KEY)")
	args = parser.parse_args()

	settings = get_settings()
	k = args.k or settings.rag_top_k
	disease_of = {str(d["id"]): d.get("disease_group", "") for d in load_documents(settings.data_path)}
	golden = load_golden()
	store = ChromaVectorStore()
	retriever = Retriever(store, mode=args.mode, rerank=args.rerank or None)

	# Câu follow-up được chấm thêm 2 lần: bản viết lại độc lập viết tay (giới hạn trên) và bản do
	# Gemini viết lại từ history (đúng như hệ thống chạy khi QUERY_REWRITE_ENABLED=true).
	queries = [(item, item["question"], "as_is") for item in golden]
	queries += [(item, item["standalone_question"], "standalone") for item in golden if item.get("standalone_question")]
	rewritten_by: dict[str, str] = {}
	if not args.no_rewrite:
		rag = RagService(GeminiService(), retriever)  # dùng đúng build_search_query của server
		for item in golden:
			if item.get("history"):
				history = trim_history([ChatMessage(**m) for m in item["history"]], settings.history_max_turns)
				rewritten_by[item["id"]] = rag.build_search_query(item["question"], history)
				queries.append((item, rewritten_by[item["id"]], "rewritten"))
	vectors = embed_texts([text for _, text, _ in queries])

	rows_by_mode: dict[str, list[dict]] = defaultdict(list)
	for (item, text, mode), vector in zip(queries, vectors):
		results = retriever.search(text, k, query_embedding=vector)
		dense_top1 = store.search(vector, 1)[0]["score"]
		rows_by_mode[mode].append(evaluate_item(item, results, disease_of, dense_top1))

	rows = rows_by_mode["as_is"]
	by_type: dict[str, list[dict]] = defaultdict(list)
	for row in rows:
		by_type[row["type"]].append(row)

	rerank = f" + rerank({settings.rerank_onnx_file}, {settings.rerank_candidates} ứng viên)" if retriever.rerank_enabled else ""
	print(f"Golden set: {len(golden)} câu | retrieval={retriever.mode}{rerank} | k={k} | "
		  f"model={settings.embedding_model} | RAG_MIN_SCORE={settings.rag_min_score}")
	print_table("Retrieval theo loại câu hỏi", {"ALL": summarize(rows, k), **{t: summarize(r, k) for t, r in sorted(by_type.items())}})
	follow_up_table = {
		"as_is": summarize(by_type["follow_up"], k),
		"standalone": summarize(rows_by_mode["standalone"], k),
	}
	if rows_by_mode["rewritten"]:
		follow_up_table["rewritten"] = summarize(rows_by_mode["rewritten"], k)
	print_table("Follow-up: nguyên văn / viết tay độc lập / Gemini viết lại", follow_up_table)
	for item_id, query in rewritten_by.items():
		print(f"  {item_id:<12} → {query}")

	answerable_top1 = sorted(r["top1_score"] for r in rows if "rank" in r and r["rank"] == 1)
	no_info_top1 = sorted(r["top1_score"] for r in rows if r["type"] in ("out_of_kb", "off_topic"))
	print("\n== Phân bố điểm top-1 (để chọn RAG_MIN_SCORE)")
	if answerable_top1:
		print(f"  Câu trả lời đúng ở top-1: min={answerable_top1[0]:.3f}  median={answerable_top1[len(answerable_top1) // 2]:.3f}")
	if no_info_top1:
		print(f"  Câu ngoài phạm vi       : max={no_info_top1[-1]:.3f}  median={no_info_top1[len(no_info_top1) // 2]:.3f}")
	leaked = [r["id"] for r in rows if r["type"] in ("out_of_kb", "off_topic") and r["kept_after_threshold"]]
	print(f"  Câu ngoài phạm vi vẫn có chunk vượt ngưỡng {settings.rag_min_score}: {len(leaked)}/{len(no_info_top1)} {leaked}")

	misses = [r for r in rows if "rank" in r and not r["rank"]]
	if misses:
		print(f"\n== Không tìm thấy tài liệu liên quan trong top-{k} ({len(misses)} câu)")
		for row in misses:
			print(f"  {row['id']:<12} {row['question']}")

	if args.out:
		args.out.write_text(json.dumps(rows_by_mode, ensure_ascii=False, indent=2), encoding="utf-8")
		print(f"\nĐã ghi chi tiết: {args.out}")


if __name__ == "__main__":
	main()
