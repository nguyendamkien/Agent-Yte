# Frontend — ChatBot Y Tế

Giao diện chat viết bằng React 19 + Vite. Gọi `POST /api/chat` của backend (xem [README gốc](../README.md)).

## Tính năng

- Chat hỏi đáp y tế, hiển thị kèm danh sách nguồn tham khảo (link bài gốc) dưới mỗi câu trả lời.
- Nhiều cuộc trò chuyện trong sidebar, lưu trong `localStorage` của trình duyệt (không lưu ở server).
- Gửi kèm lịch sử hội thoại mỗi request để chatbot nhớ ngữ cảnh.

## Chạy

```bash
npm install
copy .env.example .env    # tuỳ chọn; macOS/Linux: cp .env.example .env
npm run dev               # http://localhost:5173
```

Cần backend đang chạy (mặc định `http://localhost:8000`). Nếu backend ở địa chỉ khác, sửa trong `.env`:

```
VITE_API_BASE_URL=http://localhost:8000
```

## Lệnh

| Lệnh | Tác dụng |
|---|---|
| `npm run dev` | Chạy dev server có HMR |
| `npm run build` | Build production ra thư mục `dist/` |
| `npm run preview` | Chạy thử bản build |
| `npm run lint` | Kiểm tra code bằng Oxlint |

## Cấu trúc

```
src/
├── App.jsx                  # Giao diện chat chính, quản lý phiên và gọi API
├── api/chatApi.js           # sendChatMessage(message, history)
├── components/
│   ├── Sidebar.jsx          # Danh sách cuộc trò chuyện
│   ├── MessageBubble.jsx    # Một tin nhắn + nguồn tham khảo
│   └── ChatInput.jsx        # Ô nhập câu hỏi
└── utils/sessions.js        # Tạo / đọc / lưu phiên chat vào localStorage
```
