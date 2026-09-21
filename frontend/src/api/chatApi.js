const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

/**
 * Gửi câu hỏi tới backend và nhận câu trả lời từ chatbot.
 * @param {string} message - Câu hỏi của người dùng.
 * @param {{role: "user"|"model", content: string}[]} history - Lịch sử hội thoại trước đó.
 * @returns {Promise<{reply: string, disclaimer: string, sources: object[]}>}
 */
export async function sendChatMessage(message, history) {
  const response = await fetch(`${API_BASE_URL}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, history }),
  });

  if (!response.ok) {
    const errorBody = await response.json().catch(() => null);
    const detail = errorBody?.detail || `Lỗi máy chủ (${response.status})`;
    throw new Error(detail);
  }

  return response.json();
}
