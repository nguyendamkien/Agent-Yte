"""Gemini embedding adapter used by both indexing and retrieval."""

from collections.abc import Sequence

import google.generativeai as genai

from app.config import get_settings


def embed_texts(texts: Sequence[str], *, task_type: str = "retrieval_document") -> list[list[float]]:
	"""Create embeddings in batches through the Gemini SDK."""
	settings = get_settings()
	if not settings.gemini_api_key:
		raise RuntimeError("Thiếu GEMINI_API_KEY để tạo embedding.")
	genai.configure(api_key=settings.gemini_api_key)

	vectors: list[list[float]] = []
	for text in texts:
		result = genai.embed_content(
			model=settings.embedding_model,
			content=text,
			task_type=task_type,
		)
		embedding = result["embedding"] if isinstance(result, dict) else result.embedding
		vectors.append(list(embedding))
	return vectors


def embed_query(text: str) -> list[float]:
	return embed_texts([text], task_type="retrieval_query")[0]