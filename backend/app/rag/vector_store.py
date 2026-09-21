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

	def search(self, query_embedding: list[float], top_k: int) -> list[dict[str, Any]]:
		result = self._collection.query(
			query_embeddings=[query_embedding],
			n_results=top_k,
			include=["documents", "metadatas", "distances"],
		)
		documents = result.get("documents", [[]])[0]
		metadatas = result.get("metadatas", [[]])[0]
		distances = result.get("distances", [[]])[0]
		return [
			{
				"text": text,
				"metadata": metadata or {},
				"score": max(0.0, 1.0 - float(distance)),
			}
			for text, metadata, distance in zip(documents, metadatas, distances)
		]