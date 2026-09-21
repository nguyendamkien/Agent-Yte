from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Cấu hình ứng dụng, đọc từ biến môi trường / file .env."""

    gemini_api_key: str = ""
    gemini_model: str = "gemini-1.5-flash"
    embedding_model: str = "models/embedding-001"
    vector_db_path: str = "app/storage/chroma"
    vector_collection: str = "medical_documents"
    rag_top_k: int = 5
    rag_min_score: float = 0.25
    data_path: str = "../data-collection/data/combined.jsonl"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
