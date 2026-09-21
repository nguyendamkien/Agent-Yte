import { useEffect, useRef, useState } from "react";
import "./App.css";
import Sidebar from "./components/Sidebar";
import MessageBubble from "./components/MessageBubble";
import ChatInput from "./components/ChatInput";
import { sendChatMessage } from "./api/chatApi";
import {
  createSession,
  deriveTitle,
  loadSessions,
  saveSessions,
} from "./utils/sessions";

function App() {
  const [sessions, setSessions] = useState(() => {
    const saved = loadSessions();
    return saved?.sessions ?? [createSession()];
  });
  const [activeSessionId, setActiveSessionId] = useState(() => {
    const saved = loadSessions();
    return saved?.activeSessionId ?? sessions[0].id;
  });
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef(null);

  const activeSession =
    sessions.find((session) => session.id === activeSessionId) ?? sessions[0];

  useEffect(() => {
    saveSessions(sessions, activeSessionId);
  }, [sessions, activeSessionId]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [activeSession?.messages, isLoading]);

  function updateSessionMessages(sessionId, updater) {
    setSessions((prev) =>
      prev.map((session) =>
        session.id === sessionId
          ? { ...session, messages: updater(session.messages) }
          : session
      )
    );
  }

  async function handleSend(text) {
    const sessionId = activeSession.id;
    const userMessage = { role: "user", content: text };
    const history = activeSession.messages.map(({ role, content }) => ({
      role,
      content,
    }));

    setSessions((prev) =>
      prev.map((session) => {
        if (session.id !== sessionId) return session;
        const isFirstUserMessage = !session.messages.some((m) => m.role === "user");
        return {
          ...session,
          title: isFirstUserMessage ? deriveTitle(text) : session.title,
          messages: [...session.messages, userMessage],
        };
      })
    );
    setIsLoading(true);

    try {
      const data = await sendChatMessage(text, history);
      updateSessionMessages(sessionId, (msgs) => [
        ...msgs,
        { role: "model", content: data.reply, sources: data.sources ?? [] },
      ]);
    } catch (error) {
      updateSessionMessages(sessionId, (msgs) => [
        ...msgs,
        { role: "model", content: `Đã có lỗi xảy ra: ${error.message}`, isError: true },
      ]);
    } finally {
      setIsLoading(false);
    }
  }

  function handleNewSession() {
    const session = createSession();
    setSessions((prev) => [session, ...prev]);
    setActiveSessionId(session.id);
  }

  function handleDeleteSession(sessionId) {
    setSessions((prev) => {
      const next = prev.filter((session) => session.id !== sessionId);
      if (sessionId === activeSessionId && next.length > 0) {
        setActiveSessionId(next[0].id);
      }
      return next;
    });
  }

  return (
    <div className="app">
      <header className="app-header">
        <h1>🩺 ChatBot Y Tế</h1>
        <p>Hỏi đáp thông tin sức khỏe cùng trợ lý ảo (Gemini AI)</p>
      </header>

      <div className="app-body">
        <Sidebar
          sessions={sessions}
          activeSessionId={activeSession?.id}
          onSelectSession={setActiveSessionId}
          onNewSession={handleNewSession}
          onDeleteSession={handleDeleteSession}
        />

        <div className="app-main">
          <main className="chat-window">
            {activeSession?.messages.map((message, index) => (
              <MessageBubble
                key={index}
                role={message.role}
                content={message.content}
                isError={message.isError}
                sources={message.sources}
              />
            ))}
            {isLoading && (
              <MessageBubble role="model" content="Đang soạn câu trả lời..." />
            )}
            <div ref={messagesEndRef} />
          </main>

          <ChatInput onSend={handleSend} disabled={isLoading} />
        </div>
      </div>

      <footer className="app-footer">
        Thông tin do chatbot cung cấp chỉ mang tính tham khảo, không thay thế
        cho tư vấn, chẩn đoán của bác sĩ hoặc chuyên gia y tế.
      </footer>
    </div>
  );
}

export default App;
