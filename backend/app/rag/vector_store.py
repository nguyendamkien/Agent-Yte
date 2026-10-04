"""Chroma persistence adapter."""

from pathlib import Path
from typing import Any

from app.config import get_settings


class ChromaVectorStore:
	def __init__(self) -> None:
		try:
			import chromadb
		except ImportError as exc:
			raise RuntimeError(
				"Chưa cài chromadb. Chạy: pip install -r requirements.txt"
			) from exc

		settings = get_settings()
		path = Path(settings.vector_db_path)
		path.mkdir(parents=True, exist_ok=True)
		self._client = chromadb.PersistentClient(path=str(path))
		self._collection = self._client.get_or_create_collection(
			name=settings.vector_collection,
			metadata={"hnsw:space": "cosine"},
		)

	def reset(self) -> None:
		settings = get_settings()
		self._client.delete_collection(settings.vector_collection)
		self._collection = self._client.get_or_create_collection(
			name=settings.vector_collection,
			metadata={"hnsw:space": "cosine"},
		)

	def add(self, chunks: list[dict[str, Any]], embeddings: list[list[float]]) -> None:
		if not chunks:
			return
		self._collection.upsert(
			ids=[chunk["id"] for chunk in chunks],
			documents=[chunk["text"] for chunk in chunks],
			embeddings=embeddings,
			metadatas=[chunk["metadata"] for chunk in chunks],
		)

	def get_all(self) -> list[dict[str, Any]]:
		"""Đọc toàn bộ chunk (không kèm vector) — dùng để dựng chỉ mục BM25."""
		result = self._collection.get(include=["documents", "metadatas"])
		return [
			{"id": chunk_id, "text": text, "metadata": metadata or {}}
			for chunk_id, text, metadata in zip(result["ids"], result["documents"], result["metadatas"])
		]

	def search(self, query_embedding: list[float], top_k: int) -> list[dict[str, Any]]:
		result = self._collection.query(
			query_embeddings=[query_embedding],
			n_results=top_k,
			include=["documents", "metadatas", "distances"],
		)
		ids = result.get("ids", [[]])[0]
		documents = result.get("documents", [[]])[0]
		metadatas = result.get("metadatas", [[]])[0]
		distances = result.get("distances", [[]])[0]
		return [
			{
				"id": chunk_id,
				"text": text,
				"metadata": metadata or {},
				"score": max(0.0, 1.0 - float(distance)),
			}
			for chunk_id, text, metadata, distance in zip(ids, documents, metadatas, distances)
		]