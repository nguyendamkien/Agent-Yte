export default function MessageBubble({ role, content, isError, sources = [] }) {
  const isUser = role === "user";

  return (
    <div className={`message-row ${isUser ? "message-row--user" : "message-row--bot"}`}>
      <div
        className={[
          "message-bubble",
          isUser ? "message-bubble--user" : "message-bubble--bot",
          isError ? "message-bubble--error" : "",
        ].join(" ")}
      >
        {content}
        {!isUser && sources.length > 0 && (
          <div className="message-sources">
            <strong>Nguồn tham khảo</strong>
            {sources.map((source) => (
              <a key={source.url} href={source.url} target="_blank" rel="noreferrer">
                {source.title || source.url}
              </a>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
