"""Section-aware recursive chunking for Vietnamese medical documents.

The source data already contains semantic sections such as "Triệu chứng" and
"Điều trị", so we keep each section together when possible. Long sections are
then split recursively by paragraphs, sentences, and finally whitespace. This
preserves medical context better than splitting the whole article by character
count alone.
"""

import re
from typing import Any


def _split_text(text: str, max_chars: int, overlap_chars: int) -> list[str]:
	text = re.sub(r"\s+", " ", text).strip()
	if not text:
		return []
	if len(text) <= max_chars:
		return [text]

	pieces = re.split(r"(?<=[.!?;:])\s+", text)
	if len(pieces) == 1:
		pieces = text.split(" ")

	chunks: list[str] = []
	current = ""
	for piece in pieces:
		piece = piece.strip()
		if not piece:
			continue
		candidate = f"{current} {piece}".strip()
		if current and len(candidate) > max_chars:
			chunks.append(current)
			overlap = current[-overlap_chars:].strip() if overlap_chars else ""
			current = f"{overlap} {piece}".strip()
		else:
			current = candidate
	if current:
		chunks.append(current)
	return chunks


def chunk_documents(
	documents: list[dict[str, Any]],
	max_chars: int = 2400,
	overlap_chars: int = 300,
) -> list[dict[str, Any]]:
	"""Convert documents into embedding-ready chunks with source metadata."""
	chunks: list[dict[str, Any]] = []
	for document in documents:
		sections = document.get("sections") or []
		if not sections:
			sections = [{"heading": "Nội dung", "content": document.get("full_text", "")}]

		chunk_index = 0
		for section in sections:
			heading = str(section.get("heading") or "Nội dung").strip()
			content = str(section.get("content") or "").strip()
			for text in _split_text(content, max_chars, overlap_chars):
				chunks.append(
					{
						"id": f"{document['id']}-{chunk_index}",
						"text": f"{heading}\n{text}",
						"metadata": {
							"document_id": str(document["id"]),
							"source": str(document.get("source") or ""),
							"title": str(document.get("title") or ""),
							"category": str(document.get("category") or ""),
							"section": heading,
							"url": str(document.get("url") or ""),
							"citation": str(document.get("citation") or ""),
						},
					}
				)
				chunk_index += 1
	return chunks