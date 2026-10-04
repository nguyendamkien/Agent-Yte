"""Cross-encoder reranker: sắp xếp lại các chunk ứng viên theo độ liên quan với câu hỏi.

Vì sao cần rerank
-----------------
Bước retrieve (dense bi-encoder + BM25) phải nhanh nên chấm câu hỏi và chunk một cách
gián tiếp: bi-encoder embed câu hỏi và chunk *riêng rẽ* rồi so cosine, BM25 chỉ đếm
từ trùng. Cả hai đều không "đọc" câu hỏi cùng với chunk, nên hay đẩy lên những chunk
na ná chủ đề nhưng không trả lời đúng câu hỏi.

Cross-encoder khác ở chỗ ghép cặp [câu hỏi] + [chunk] thành MỘT đầu vào và cho qua
transformer, để attention nhìn thấy tương tác giữa từng từ của câu hỏi với từng từ của
chunk, rồi xuất ra một điểm liên quan:

    bi-encoder:     emb(q) ──┐
                             ├─ cosine        (q và d mã hoá độc lập, tính trước được)
                    emb(d) ──┘
    cross-encoder:  model(<s> q </s></s> d </s>) → logit → sigmoid → điểm 0–1
                    (phải chạy cho từng cặp, không tính trước được)

Chính xác hơn nhiều nhưng tốn: mỗi cặp là một lượt chạy model. Vì vậy chỉ rerank một
nhóm nhỏ ứng viên (RERANK_CANDIDATES, mặc định 20 chunk sau RRF), rồi giữ lại top-k:

    câu hỏi → hybrid retrieve (nhanh, lấy rộng ~20) → cross-encoder (chậm, chấm kỹ) → top-k

Model
-----
BAAI/bge-reranker-v2-m3: cross-encoder đa ngôn ngữ (có tiếng Việt), nền XLM-RoBERTa,
~568M tham số, đầu vào tối đa 8192 token. Đầu ra là một logit; sigmoid(logit) cho điểm
0–1 (0.5 ≈ ranh giới liên quan / không liên quan), tiện đặt ngưỡng về sau.

Cách chạy
---------
ONNX Runtime + thư viện tokenizers, KHÔNG dùng PyTorch (trên máy phát triển, Smart App
Control của Windows chặn torch.dll; DLL của onnxruntime do Microsoft ký nên chạy được).
Dùng bản chuyển đổi onnx-community/bge-reranker-v2-m3-ONNX (tổ chức của Hugging Face),
mặc định file onnx/model_int8.onnx: lượng tử hoá int8, ~571 MB, nhanh hơn nhiều trên
CPU, sai khác không đáng kể so với fp32; đổi RERANK_ONNX_FILE=onnx/model.onnx để dùng
bản fp32 (~2.3 GB). Tải về tự động lần đầu vào cache của Hugging Face.

Bật bằng RERANK_ENABLED=true trong .env.

Tốc độ (đo trên CPU 8 nhân, bản int8, không GPU): ~0.8 giây cho mỗi cặp 512 token, tức
~24 s/câu hỏi với 20 ứng viên × 1024 token, ~11.5 s/câu với 10 ứng viên × 1024 token.
Số luồng ONNX Runtime mặc định đã tối ưu; batch không giúp thêm. Chậm như vậy là do
cỡ model (568M) chạy trên CPU; có GPU thì nhanh hơn nhiều.
"""

from functools import lru_cache
from typing import Any, Protocol

from app.config import get_settings

# Chunk dài nhất ~1.800 token; 1024 đủ cho phần lớn chunk và giữ tốc độ trên CPU.
# Khi vượt, chỉ cắt phần chunk (câu hỏi luôn được giữ nguyên).
MAX_LENGTH = 1024
BATCH_SIZE = 8


class _PairScorer(Protocol):
	def predict(self, pairs: list[tuple[str, str]]) -> list[float]:
		"""Trả về điểm liên quan 0–1 cho từng cặp (câu hỏi, chunk)."""
		...


class OnnxCrossEncoder:
	"""Chạy cross-encoder bằng ONNX Runtime, không phụ thuộc PyTorch."""

	def __init__(self, repo_id: str, onnx_file: str, max_length: int = MAX_LENGTH) -> None:
		import numpy as np
		import onnxruntime as ort
		from huggingface_hub import hf_hub_download
		from tokenizers import Tokenizer

		self._np = np
		model_path = hf_hub_download(repo_id, onnx_file)
		if onnx_file == "onnx/model.onnx":  # bản fp32 lưu trọng số ở file .onnx_data đi kèm
			hf_hub_download(repo_id, "onnx/model.onnx_data")
		self._tokenizer = Tokenizer.from_file(hf_hub_download(repo_id, "tokenizer.json"))
		# Cặp (q, d): chỉ cắt vế thứ hai (chunk); pad theo câu dài nhất trong batch.
		self._tokenizer.enable_truncation(max_length=max_length, strategy="only_second")
		self._tokenizer.enable_padding(pad_id=self._tokenizer.token_to_id("<pad>"), pad_token="<pad>")
		self._session = ort.InferenceSession(model_path, providers=["CPUExecutionProvider"])
		self._input_names = {i.name for i in self._session.get_inputs()}

	def predict(self, pairs: list[tuple[str, str]]) -> list[float]:
		np = self._np
		scores: list[float] = []
		for start in range(0, len(pairs), BATCH_SIZE):
			encodings = self._tokenizer.encode_batch(pairs[start : start + BATCH_SIZE])
			feeds = {
				"input_ids": np.array([e.ids for e in encodings], dtype=np.int64),
				"attention_mask": np.array([e.attention_mask for e in encodings], dtype=np.int64),
			}
			feeds = {name: value for name, value in feeds.items() if name in self._input_names}
			logits = self._session.run(None, feeds)[0].reshape(-1)
			scores.extend((1.0 / (1.0 + np.exp(-logits))).tolist())  # sigmoid
		return scores


class CrossEncoderReranker:
	def __init__(self, model: _PairScorer) -> None:
		self._model = model

	def rerank(self, query: str, candidates: list[dict], top_k: int) -> list[dict]:
		"""Chấm lại từng cặp (query, chunk), trả về top_k chunk có điểm cao nhất.

		Mỗi chunk trả về được gắn thêm scores["rerank"] (0–1) và score = điểm rerank;
		các điểm cũ (dense, bm25, rrf...) giữ nguyên trong scores để debug.
		"""
		if not candidates:
			return []
		pairs = [(query, candidate["text"]) for candidate in candidates]
		reranked = []
		for candidate, score in zip(candidates, self._model.predict(pairs)):
			item = {**candidate, "scores": {**candidate.get("scores", {}), "rerank": float(score)}}
			item["score"] = float(score)
			reranked.append(item)
		reranked.sort(key=lambda item: item["score"], reverse=True)
		return reranked[:top_k]


@lru_cache
def get_reranker() -> CrossEncoderReranker:
	"""Nạp model một lần cho cả tiến trình (nạp model tốn vài giây và vài trăm MB RAM)."""
	settings = get_settings()
	return CrossEncoderReranker(OnnxCrossEncoder(settings.rerank_onnx_repo, settings.rerank_onnx_file))
