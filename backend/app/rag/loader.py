"""Load crawled medical documents from JSONL."""

import json
from pathlib import Path
from typing import Any, Iterator


def load_documents(path: str | Path) -> Iterator[dict[str, Any]]:
	"""Yield valid documents from a UTF-8 JSONL file."""
	data_path = Path(path)
	if not data_path.exists():
		raise FileNotFoundError(f"Không tìm thấy file dữ liệu: {data_path}")

	with data_path.open("r", encoding="utf-8") as file:
		for line_number, line in enumerate(file, start=1):
			if not line.strip():
				continue
			try:
				document = json.loads(line)
			except json.JSONDecodeError as exc:
				raise ValueError(
					f"JSON không hợp lệ tại dòng {line_number}: {exc}"
				) from exc
			if not isinstance(document, dict):
				continue
			if document.get("id") and document.get("full_text"):
				yield document