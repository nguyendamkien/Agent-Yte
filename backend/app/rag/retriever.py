"""Retrieve relevant medical chunks."""

from app.config import get_settings
from app.rag.embeddings import embed_query
from app.rag.vector_store import ChromaVectorStore


class Retriever:
	def __init__(self, store: ChromaVectorStore | None = None) -> None:
		self._store = store or ChromaVectorStore()

	def search(self, query: str, top_k: int | None = None) -> list[dict]:
		settings = get_settings()
		results = self._store.search(embed_query(query), top_k or settings.rag_top_k)
		return [result for result in results if result["score"] >= settings.rag_min_score]