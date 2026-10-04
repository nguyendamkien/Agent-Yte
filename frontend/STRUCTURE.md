# Cấu trúc Frontend (React + Vite)

## Cây thư mục

```
frontend/
├── index.html                     # HTML gốc, chứa <div id="root"> để React render vào
├── vite.config.js                 # Cấu hình build tool Vite
├── .env.example                   # Mẫu cấu hình (VITE_API_BASE_URL trỏ tới backend)
└── src/
    ├── main.jsx                   # Điểm khởi động: render <App /> vào DOM
    ├── App.jsx                    # Component gốc — quản lý state session + layout tổng
    ├── App.css                    # Style cho toàn bộ layout (header/sidebar/chat/footer)
    ├── index.css                  # CSS reset tối giản, áp cho toàn trang
    ├── api/
    │   └── chatApi.js             # Gọi backend: fetch POST /api/chat/stream, đọc stream SSE
    ├── components/
    │   ├── Sidebar.jsx            # Danh sách session + nút "Cuộc trò chuyện mới"
    │   ├── MessageBubble.jsx      # 1 bong bóng chat; câu trả lời của bot render markdown (react-markdown)
    │   └── ChatInput.jsx          # Ô nhập tin nhắn + nút Gửi
    └── utils/
        └── sessions.js            # Tạo/đọc/ghi session vào localStorage
```

## Cây component (ai render ai)

```
main.jsx
  └── App.jsx                       (state: sessions[], activeSessionId, isLoading)
        ├── <header>                 tiêu đề app
        ├── <Sidebar>                 nhận sessions + activeSessionId, callback chọn/tạo/xoá
        ├── <main class="chat-window">
        │     └── <MessageBubble> × N  (1 cái mỗi tin nhắn trong session đang mở)
        ├── <ChatInput>               callback onSend(text) → App.handleSend
        └── <footer>                 disclaimer y tế cố định
```

## Luồng dữ liệu khi gửi 1 tin nhắn

```
Người dùng gõ câu hỏi, bấm Gửi
    ▼
ChatInput.handleSubmit          — validate không rỗng, gọi onSend(text), rồi tự xoá input
    ▼
App.handleSend(text)
    │  1. Thêm { role: "user", content: text } và một bong bóng trả lời rỗng
    │     { role: "model", content: "", pending: true, status } vào session đang mở
    │     (nếu là tin nhắn đầu tiên → tự đặt tên session theo nội dung câu hỏi)
    │  2. setIsLoading(true) → khoá ô nhập
    │  3. Gọi streamChatMessage(text, history, handlers)  [api/chatApi.js]
    ▼
chatApi.streamChatMessage        — fetch POST {API_BASE_URL}/api/chat/stream, đọc từng sự kiện SSE:
    │   status  → bong bóng hiện "Đang phân tích câu hỏi… / Đang tìm tài liệu… / Đang soạn…"
    │   sources → lưu nguồn (chỉ hiện khi đã có chữ)
    │   delta   → nối thêm chữ vào content, bong bóng render markdown + con trỏ nhấp nháy
    │   done    → bỏ cờ pending;  error → bong bóng lỗi (hoặc giữ phần đã có + ghi chú bị ngắt)
    ▼
useEffect trong App.jsx         — mỗi lần messages đổi, tự saveSessions() vào localStorage
                                    và cuộn khung chat xuống cuối
```

## Giải thích từng file

### `src/main.jsx`
File khởi động chuẩn của Vite — lấy `<div id="root">` trong `index.html`, render `<App />` vào đó (bọc trong `<StrictMode>` để React cảnh báo sớm các pattern không an toàn khi dev).

### `src/App.jsx`
Component gốc, giữ toàn bộ **state chính** của app:
- `sessions`: mảng các cuộc trò chuyện, mỗi session có `{ id, title, createdAt, messages[] }`. Khởi tạo bằng cách đọc từ `localStorage` (`loadSessions()`), nếu chưa có gì thì tạo 1 session mới.
- `activeSessionId`: id session đang mở trên màn hình.
- `isLoading`: đang chờ phản hồi từ backend hay không (để disable input + hiện bong bóng "đang soạn").

Các hàm xử lý chính:
- `handleSend(text)`: xem sơ đồ luồng dữ liệu ở trên.
- `handleNewSession()` / `handleDeleteSession(id)`: thêm/xoá session, tự chuyển `activeSessionId` sang session hợp lý khi xoá session đang mở.

Có 2 `useEffect`:
- Tự động `saveSessions()` vào `localStorage` mỗi khi `sessions` hoặc `activeSessionId` đổi — nhờ vậy F5 lại trang không mất lịch sử chat.
- Tự cuộn khung chat xuống tin nhắn mới nhất mỗi khi có tin nhắn mới hoặc đổi trạng thái loading.

### `src/components/Sidebar.jsx`
Component "dumb" (không giữ state riêng) — nhận toàn bộ dữ liệu + callback từ `App.jsx` qua props:
`sessions`, `activeSessionId`, `onSelectSession`, `onNewSession`, `onDeleteSession`. Render nút tạo session mới và danh sách session (nút xoá chỉ hiện khi còn hơn 1 session, để luôn giữ ít nhất 1 cuộc trò chuyện).

### `src/components/MessageBubble.jsx`
Component thuần hiển thị — nhận `role` ("user" | "model"), `content`, `isError`; tự chọn class CSS để bong bóng lệch phải (user, màu xanh) hay lệch trái (bot, màu trắng), đổi màu đỏ nếu `isError`.

### `src/components/ChatInput.jsx`
Giữ state cục bộ `value` cho ô input. Khi submit form: trim() nội dung, nếu rỗng hoặc đang `disabled` (đang loading) thì bỏ qua; ngược lại gọi `onSend(trimmed)` rồi tự xoá ô input.

### `src/api/chatApi.js`
Hàm `streamChatMessage(message, history, { onStatus, onSources, onDelta })` — nơi **duy nhất** trong frontend gọi ra backend. Đọc `API_BASE_URL` từ biến môi trường `VITE_API_BASE_URL` (fallback `http://localhost:8000` nếu không set).
- Dùng `fetch` + `ReadableStream` thay vì `EventSource` vì `EventSource` chỉ gửi được GET.
- Tách stream theo dòng trống (`\n\n`), mỗi khối là một sự kiện `event:` / `data:` (JSON) rồi gọi handler tương ứng. Promise resolve ở sự kiện `done`, reject khi gặp sự kiện `error` hoặc stream đóng giữa chừng.
- Nếu response không `ok` (lỗi trước khi stream, vd 500 thiếu API key), cố đọc field `detail` trong JSON lỗi để hiện thông báo dễ hiểu hơn.

### `src/utils/sessions.js`
Tách riêng logic liên quan tới `localStorage` khỏi `App.jsx`:
- `WELCOME_MESSAGE`: tin nhắn chào mặc định khi tạo session mới.
- `createSession()`: tạo object session mới với `id` random (`crypto.randomUUID()`).
- `loadSessions()` / `saveSessions()`: đọc/ghi vào `localStorage` dưới key `chatbot-y-te-sessions`, có `try/catch` để không crash app nếu trình duyệt chặn localStorage (vd. chế độ ẩn danh). Khi đọc, bong bóng còn `pending` (trang bị tải lại giữa lúc stream) được đóng lại thay vì hiện trạng thái chờ mãi.
- `deriveTitle(text)`: cắt câu hỏi đầu tiên còn tối đa 32 ký tự để làm tên session hiển thị trên Sidebar.

### `App.css` / `index.css`
- `index.css`: reset tối giản áp dụng toàn trang (font, bỏ margin mặc định của `body`, cho `#root` cao 100vh).
- `App.css`: toàn bộ style cho layout — dùng CSS Grid 3 hàng (header/body/footer) ở `.app`, trong đó `.app-body` lại là grid 2 cột (sidebar 260px + khu chat chiếm phần còn lại). Màu chủ đạo là teal `#0f9d8c` (nút, bong bóng chat của user, mục sidebar đang chọn) phối với nền trắng/xám nhạt.

## Vì sao tách như vậy?

- **State tập trung ở `App.jsx`**, các component con (`Sidebar`, `MessageBubble`, `ChatInput`) đều là "dumb component" chỉ nhận props và gọi callback — dễ test, dễ đọc, không có state rải rác nhiều nơi gây khó đồng bộ (vd. sessions phải nhất quán giữa Sidebar và khung chat).
- **`api/` tách riêng khỏi component**: nếu sau này đổi cách gọi backend (thêm header auth, đổi sang GraphQL...), chỉ sửa `chatApi.js`, không đụng vào UI.
- **`utils/sessions.js` tách khỏi `App.jsx`**: logic đọc/ghi `localStorage` là chi tiết triển khai, không liên quan tới việc render UI — tách ra giúp `App.jsx` tập trung vào logic "chat" thay vì logic "lưu trữ".
