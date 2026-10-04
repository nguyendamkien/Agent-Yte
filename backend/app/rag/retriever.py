"""Hybrid retrieval: BM25 (từ khoá) + dense (ngữ nghĩa), gộp bằng RRF, tuỳ chọn rerank.

Luồng xử lý một câu hỏi (RETRIEVAL_MODE=hybrid):

    câu hỏi ─┬─► Dense: embed câu hỏi → Chroma (cosine) ─► top-N ─┐
             │                                                     ├─► RRF ─► [rerank] ─► top-k
             └─► BM25: tách token → chỉ mục BM25 trong RAM ─► top-N ┘

1. Dense (ngữ nghĩa) — text-embedding-3-small + Chroma HNSW, khoảng cách cosine.
   Hiểu từ đồng nghĩa / cách diễn đạt khác ("cao huyết áp" ≈ "tăng huyết áp"),
   nhưng dễ bỏ lỡ thuật ngữ hiếm, mã xét nghiệm, tên thuốc ("tophi", "HBsAg").

2. BM25 (từ khoá) — xem app/rag/bm25.py. Bắt chính xác thuật ngữ hiếm nhờ IDF,
   nhưng không hiểu đồng nghĩa. Chỉ mục dựng trong RAM từ chính các chunk trong
   Chroma lúc khởi tạo Retriever, nên luôn khớp với index hiện tại.

3. Gộp bằng Reciprocal Rank Fusion (RRF). Điểm BM25 (vd 12.7) và cosine (vd 0.68)
   nằm trên hai thang khác nhau nên không cộng thẳng được; RRF chỉ dùng THỨ HẠNG:

       rrf(d) = Σ_{nhánh r chứa d}  1 / (RRF_K + rank_r(d))        (rank bắt đầu từ 1)

   - Chunk xếp cao ở cả hai nhánh → điểm cao nhất.
   - Chunk chỉ có ở một nhánh vẫn được tính (nhánh kia đóng góp 0), nên thuật ngữ hiếm
     mà dense bỏ lỡ vẫn có cơ hội lọt top.
   - RRF_K = 60 (giá trị chuẩn trong tài liệu gốc của RRF) làm phẳng chênh lệch giữa
     hạng 1 và hạng 2, để một nhánh không lấn át hoàn toàn nhánh kia.
   - Mỗi nhánh lấy RAG_CANDIDATES (mặc định 20) ứng viên trước khi gộp.

4. Rerank (tuỳ chọn, RERANK_ENABLED=true) — cross-encoder chấm lại RERANK_CANDIDATES
   ứng viên RRF tốt nhất rồi giữ top-k (xem app/rag/reranker.py). Tắt thì lấy top-k
   theo điểm RRF.

5. Ngưỡng "không có tài liệu phù hợp" (áp cho cả câu hỏi, không cho từng chunk):
   - Luôn kiểm tra trước: cosine tốt nhất của nhánh dense < RAG_MIN_SCORE → trả về rỗng.
   - Khi bật rerank, thêm: điểm rerank tốt nhất < RERANK_MIN_SCORE → trả về rỗng. Đo trên
     golden set: câu có đáp án đúng có điểm rerank ≥ 0.73, câu ngoài phạm vi ≤ 0.17, trong
     khi cosine của hai nhóm chồng lên nhau (0.48 và 0.52) nên không tách được.

Mỗi chunk trả về có:
    score   điểm dùng để xếp hạng cuối cùng (rerank nếu bật, ngược lại là RRF)
    scores  điểm từng thành phần để debug: dense, bm25, dense_rank, bm25_rank, rrf, rerank

RETRIEVAL_MODE=dense giữ hành vi cũ: chỉ dense, lọc từng chunk theo RAG_MIN_SCORE.
Sau khi chạy lại ingest cần khởi động lại server để dựng lại chỉ mục BM25.
"""

from app.config import get_settings
from app.rag.bm25 import BM25Index
from app.rag.embeddings import embed_query
from app.rag.reranker import get_reranker
from app.rag.vector_store import ChromaVectorStore


def reciprocal_rank_fusion(rankings: dict[str, list[str]], k: int) -> dict[str, float]:
	"""Gộp nhiều danh sách chunk_id đã xếp hạng thành {chunk_id: điểm RRF}."""
	fused: dict[str, float] = {}
	for ranking in rankings.values():
		for rank, chunk_id in enumerate(ranking, start=1):
			fused[chunk_id] = fused.get(chunk_id, 0.0) + 1.0 / (k + rank)
	return fused


class Retriever:
	def __init__(self, store: ChromaVectorStore | None = None, mode: str | None = None, rerank: bool | None = None) -> None:
		settings = get_settings()
		self._store = store or ChromaVectorStore()
		self.mode = mode or settings.retrieval_mode
		self.rerank_enabled = settings.rerank_enabled if rerank is None else rerank
		if self.mode not in ("dense", "hybrid"):
			raise ValueError(f"RETRIEVAL_MODE không hợp lệ: {self.mode} (chọn 'dense' hoặc 'hybrid')")

		self._chunks: dict[str, dict] = {}
		self._bm25: BM25Index | None = None
		if self.mode == "hybrid":
			# Dựng BM25 từ đúng các chunk đang có trong Chroma (vài trăm ms với vài chục nghìn chunk).
			for chunk in self._store.get_all():
				self._chunks[chunk["id"]] = chunk
			ids = list(self._chunks)
			self._bm25 = BM25Index(ids, [self._chunks[i]["text"] for i in ids])

	def search(self, query: str, top_k: int | None = None, query_embedding: list[float] | None = None) -> list[dict]:
		"""`query_embedding` cho phép truyền sẵn vector (script đánh giá embed theo lô)."""
		settings = get_settings()
		top_k = top_k or settings.rag_top_k
		embedding = query_embedding or embed_query(query)
		if self.mode == "dense":
			results = self._store.search(embedding, top_k)
			return [result for result in results if result["score"] >= settings.rag_min_score]
		return self._hybrid_search(query, embedding, top_k)

	def _hybrid_search(self, query: str, embedding: list[float], top_k: int) -> list[dict]:
		settings = get_settings()
		n_candidates = max(settings.rag_candidates, top_k)

		# Nhánh 1 — dense: top-N theo cosine.
		dense_hits = self._store.search(embedding, n_candidates)
		if not dense_hits or dense_hits[0]["score"] < settings.rag_min_score:
			return []  # không có chunk nào đủ gần về ngữ nghĩa → coi như ngoài phạm vi dữ liệu

		# Nhánh 2 — BM25: top-N theo từ khoá.
		bm25_hits = self._bm25.search(query, n_candidates) if self._bm25 else []

		# Gộp: RRF trên thứ hạng của hai nhánh.
		rankings = {
			"dense": [hit["id"] for hit in dense_hits],
			"bm25": [chunk_id for chunk_id, _ in bm25_hits],
		}
		fused = reciprocal_rank_fusion(rankings, settings.rrf_k)

		# Gắn điểm thành phần để debug / đánh giá.
		dense_by_id = {hit["id"]: (rank, hit["score"]) for rank, hit in enumerate(dense_hits, start=1)}
		bm25_by_id = {chunk_id: (rank, score) for rank, (chunk_id, score) in enumerate(bm25_hits, start=1)}
		candidates = []
		for chunk_id, rrf_score in sorted(fused.items(), key=lambda item: item[1], reverse=True):
			chunk = self._chunks.get(chunk_id) or next(hit for hit in dense_hits if hit["id"] == chunk_id)
			dense_rank, dense_score = dense_by_id.get(chunk_id, (None, None))
			bm25_rank, bm25_score = bm25_by_id.get(chunk_id, (None, None))
			candidates.append({
				"id": chunk_id,
				"text": chunk["text"],
				"metadata": chunk["metadata"],
				"score": rrf_score,
				"scores": {
					"rrf": rrf_score,
					"dense": dense_score,
					"dense_rank": dense_rank,
					"bm25": bm25_score,
					"bm25_rank": bm25_rank,
				},
			})

		# Rerank (tuỳ chọn): cross-encoder chấm lại RERANK_CANDIDATES ứng viên RRF tốt nhất.
		if self.rerank_enabled:
			reranked = get_reranker().rerank(query, candidates[: settings.rerank_candidates], top_k)
			# Điểm cross-encoder tách "liên quan / không liên quan" rõ hơn cosine nhiều, nên dùng nó
			# làm ngưỡng "không có tài liệu phù hợp" thay cho RAG_MIN_SCORE.
			if not reranked or reranked[0]["score"] < settings.rerank_min_score:
				return []
			return reranked
		return candidates[:top_k]
