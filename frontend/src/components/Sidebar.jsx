export default function Sidebar({
  sessions,
  activeSessionId,
  onSelectSession,
  onNewSession,
  onDeleteSession,
}) {
  return (
    <aside className="sidebar">
      <button className="sidebar__new-btn" onClick={onNewSession}>
        + Cuộc trò chuyện mới
      </button>

      <div className="sidebar__list">
        {sessions.map((session) => (
          <div
            key={session.id}
            className={
              "sidebar__item" +
              (session.id === activeSessionId ? " sidebar__item--active" : "")
            }
            onClick={() => onSelectSession(session.id)}
          >
            <span className="sidebar__item-title">{session.title}</span>
            {sessions.length > 1 && (
              <button
                className="sidebar__item-delete"
                title="Xóa cuộc trò chuyện"
                onClick={(event) => {
                  event.stopPropagation();
                  onDeleteSession(session.id);
                }}
              >
                ×
              </button>
            )}
          </div>
        ))}
      </div>
    </aside>
  );
}
