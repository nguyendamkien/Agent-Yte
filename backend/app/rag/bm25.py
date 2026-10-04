"""In-memory BM25 index for the lexical half of hybrid retrieval.

BM25 chấm điểm một chunk theo các từ của câu hỏi xuất hiện trong chunk:

    score(q, d) = Σ_{t ∈ q}  IDF(t) · tf(t, d) · (k1 + 1) / (tf(t, d) + k1 · (1 − b + b · |d| / avgdl))

    IDF(t) = ln(1 + (N − df(t) + 0.5) / (df(t) + 0.5))

- IDF: từ hiếm ("tophi", "hbsag") được điểm cao, từ phổ biến ("bệnh", "người") gần 0.
- tf bão hoà theo k1: xuất hiện nhiều lần có lợi nhưng tăng chậm dần.
- b chuẩn hoá độ dài: chunk dài không được lợi chỉ vì chứa nhiều chữ.

Tách token cho tiếng Việt: không dùng bộ tách từ (pyvi/underthesea) để khỏi thêm
phụ thuộc; thay vào đó lấy âm tiết đơn + cặp âm tiết liền kề (bigram). Bigram giữ
được từ ghép như "huyết_áp", "suy_thận", nên "áp" trong "áp xe" không khớp nhầm với
"huyết áp" ở mức bigram.
"""

import math
import re
from collections import Counter, defaultdict

# Hư từ xuất hiện ở hầu hết chunk, bỏ đi để giảm nhiễu (IDF của chúng vốn đã rất thấp).
STOPWORDS = frozenset(
	"là và của có cho các những được thì mà với này đó khi nào gì không bị để trong "
	"một như từ hay hoặc nên cần rất cũng đã sẽ đang vì do nếu thế tôi bạn ra vào lại "
	"theo về trên dưới sau trước hơn nhiều ít".split()
)

_TOKEN_RE = re.compile(r"\w+", re.UNICODE)


def tokenize(text: str) -> list[str]:
	syllables = [s for s in _TOKEN_RE.findall(text.lower()) if s not in STOPWORDS]
	bigrams = [f"{a}_{b}" for a, b in zip(syllables, syllables[1:])]
	return syllables + bigrams


class BM25Index:
	def __init__(self, ids: list[str], texts: list[str], k1: float = 1.5, b: float = 0.75) -> None:
		self._ids = ids
		self._k1 = k1
		self._b = b
		self._doc_len: list[int] = []
		# Inverted index: token -> [(vị trí chunk, tần suất)], chỉ duyệt các chunk có chứa token.
		self._postings: dict[str, list[tuple[int, int]]] = defaultdict(list)
		for position, text in enumerate(texts):
			counts = Counter(tokenize(text))
			self._doc_len.append(sum(counts.values()))
			for token, freq in counts.items():
				self._postings[token].append((position, freq))
		n_docs = len(texts)
		self._avgdl = sum(self._doc_len) / n_docs if n_docs else 0.0
		self._idf = {
			token: math.log(1 + (n_docs - len(posting) + 0.5) / (len(posting) + 0.5))
			for token, posting in self._postings.items()
		}

	def __len__(self) -> int:
		return len(self._ids)

	def search(self, query: str, top_n: int) -> list[tuple[str, float]]:
		"""Trả về [(chunk_id, bm25_score)] giảm dần, chỉ gồm chunk có điểm > 0."""
		scores: dict[int, float] = defaultdict(float)
		for token in set(tokenize(query)):
			idf = self._idf.get(token)
			if idf is None:
				continue
			for position, freq in self._postings[token]:
				norm = self._k1 * (1 - self._b + self._b * self._doc_len[position] / self._avgdl)
				scores[position] += idf * freq * (self._k1 + 1) / (freq + norm)
		ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)[:top_n]
		return [(self._ids[position], score) for position, score in ranked]
