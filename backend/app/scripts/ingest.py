"""Backward-compatible entry point for building the vector index."""

from app.scripts.build_index import build_index


if __name__ == "__main__":
	print(f"Hoàn tất: {build_index()} chunks")