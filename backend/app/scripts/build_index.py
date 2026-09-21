"""Build the persistent Chroma index from crawled JSONL data."""

from pathlib import Path

from app.config import get_settings
from app.rag.chunker import chunk_documents
from app.rag.embeddings import embed_texts
from app.rag.loader import load_documents
from app.rag.vector_store import ChromaVectorStore


def build_index() -> int:
	settings = get_settings()
	data_path = Path(settings.data_path)
	documents = list(load_documents(data_path))
	chunks = chunk_documents(documents)
	if not chunks:
		raise RuntimeError("Không tạo được chunk nào từ dữ liệu đầu vào.")

	store = ChromaVectorStore()
	store.reset()
	batch_size = 32
	for start in range(0, len(chunks), batch_size):
		batch = chunks[start : start + batch_size]
		embeddings = embed_texts([chunk["text"] for chunk in batch])
		store.add(batch, embeddings)
		print(f"Đã index {min(start + batch_size, len(chunks))}/{len(chunks)} chunks")
	return len(chunks)


if __name__ == "__main__":
	print(f"Hoàn tất: {build_index()} chunks")