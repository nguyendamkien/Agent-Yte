from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Cấu hình ứng dụng, đọc từ biến môi trường / file .env."""

    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.1-flash-lite"
    openai_api_key: str = ""
    embedding_model: str = "text-embedding-3-small"
    vector_db_path: str = "app/storage/chroma"
    vector_collection: str = "medical_documents"
    rag_top_k: int = 5
    rag_min_score: float = 0.25
    # Retrieval: "hybrid" (BM25 + dense, gộp bằng RRF) hoặc "dense" (chỉ vector)
    retrieval_mode: str = "hybrid"
    rag_candidates: int = 20  # số ứng viên mỗi nhánh lấy về trước khi gộp / rerank
    rrf_k: int = 60
    # Rerank bằng cross-encoder bge-reranker-v2-m3 (xem app/rag/reranker.py)
    # Bật mặc định: các số đo trong docs/RAG_EVAL.md đều chạy với rerank; tắt thì câu ngoài phạm vi
    # không bị chặn ở retrieval (RAG_MIN_SCORE theo cosine gần như không lọc được).
    rerank_enabled: bool = True
    rerank_onnx_repo: str = "onnx-community/bge-reranker-v2-m3-ONNX"
    rerank_onnx_file: str = "onnx/model_int8.onnx"  # "onnx/model.onnx" = bản fp32 (~2.3 GB)
    rerank_candidates: int = 10  # số ứng viên RRF đưa vào cross-encoder (ít hơn → nhanh hơn)
    rerank_min_score: float = 0.4  # điểm rerank tốt nhất < ngưỡng → coi như không có tài liệu phù hợp
    # Hội thoại: viết lại câu hỏi nối tiếp thành câu độc lập trước khi retrieve
    # ("Vậy điều trị thế nào?" → "Điều trị bệnh gout thế nào?"), và chỉ giữ N lượt hỏi–đáp gần nhất.
    query_rewrite_enabled: bool = True
    history_max_turns: int = 10
    data_path: str = "../data-collection/data/benh_pho_bien_10.jsonl"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
