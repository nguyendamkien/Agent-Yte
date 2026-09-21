const STORAGE_KEY = "chatbot-y-te-sessions";

export const WELCOME_MESSAGE = {
  role: "model",
  content:
    "Xin chào! Tôi là trợ lý ảo hỗ trợ hỏi đáp thông tin y tế. Bạn có thể hỏi tôi về " +
    "triệu chứng, bệnh lý phổ biến, cách chăm sóc sức khỏe... Lưu ý: thông tin chỉ mang " +
    "tính tham khảo, không thay thế chẩn đoán của bác sĩ.",
};

export function createSession() {
  return {
    id: crypto.randomUUID(),
    title: "Cuộc trò chuyện mới",
    createdAt: Date.now(),
    messages: [WELCOME_MESSAGE],
  };
}

export function loadSessions() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (Array.isArray(parsed.sessions) && parsed.sessions.length > 0) {
      return parsed;
    }
    return null;
  } catch {
    return null;
  }
}

export function saveSessions(sessions, activeSessionId) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ sessions, activeSessionId }));
  } catch {
    // localStorage không khả dụng (chế độ ẩn danh...), bỏ qua.
  }
}

/** Rút gọn tin nhắn đầu tiên của người dùng để đặt làm tiêu đề session. */
export function deriveTitle(text) {
  const trimmed = text.trim();
  return trimmed.length > 32 ? `${trimmed.slice(0, 32)}…` : trimmed;
}
