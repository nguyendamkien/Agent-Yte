from app.rag.prompt import build_context, build_rag_prompt
from app.rag.retriever import Retriever
from app.schemas import ChatMessage, Source
from app.services.gemini_service import GeminiService


class RagService:
    def __init__(self, gemini: GeminiService, retriever: Retriever) -> None:
        self._gemini = gemini
        self._retriever = retriever

    def ask(self, message: str, history: list[ChatMessage]) -> tuple[str, list[Source]]:
        results = self._retriever.search(message)
        prompt = build_rag_prompt(message, build_context(results))
        reply = self._gemini.ask(prompt, history)
        sources = [
            Source(
                title=result["metadata"].get("title", ""),
                url=result["metadata"].get("url", ""),
                citation=result["metadata"].get("citation") or None,
            )
            for result in results
            if result["metadata"].get("url")
        ]
        return reply, sources


_service: RagService | None = None


def get_rag_service() -> RagService:
    global _service
    if _service is None:
        _service = RagService(GeminiService(), Retriever())
    return _service