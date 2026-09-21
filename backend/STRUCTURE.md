# Cấu trúc Backend (FastAPI)

## Cây thư mục

```
backend/
├── main.py                        # Điểm khởi động app: tạo FastAPI instance, gắn CORS, gắn router
├── requirements.txt                # Danh sách thư viện Python cần cài
├── .env.example                    # Mẫu file cấu hình (copy thành .env rồi điền key thật)
└── app/
    ├── config.py                   # Đọc cấu hình từ .env (Settings)
    ├── schemas.py                  # Định nghĩa request/response body (Pydantic models)
    ├── routers/
    │   └── chat.py                 # Endpoint POST /api/chat
    └── services/
        └── gemini_service.py       # Logic gọi Google Gemini API
```

## Luồng xử lý 1 request chat

```
Frontend (React)
    │  POST /api/chat  { message, history }
    ▼
main.py                    — app FastAPI nhận request, CORS middleware kiểm tra origin
    ▼
app/routers/chat.py        — validate body theo ChatRequest, gọi GeminiService
    ▼
app/services/gemini_service.py
    │  - build lại lịch sử hội thoại theo format Gemini SDK
    │  - gửi kèm SYSTEM_INSTRUCTION (luật trả lời an toàn y tế)
    │  - gọi model.start_chat(...).send_message(message)
    ▼
Google Gemini API          — sinh câu trả lời
    ▼
app/routers/chat.py        — bọc kết quả vào ChatResponse { reply, disclaimer }
    ▼
Frontend nhận JSON, hiển thị lên khung chat
```

## Giải thích từng file

### `main.py`
- Tạo instance `FastAPI()` — đây là app chính, được `uvicorn` chạy (`uvicorn main:app`).
- Gắn `CORSMiddleware` để cho phép frontend (chạy ở origin khác, vd. `localhost:5173`) gọi API — danh sách origin được phép đọc từ `Settings.cors_origins_list`.
- `app.include_router(chat.router)` — gắn toàn bộ endpoint khai báo trong `app/routers/chat.py` vào app.
- Có sẵn `GET /` làm health-check, trả về `{"status": "ok", ...}` để kiểm tra server còn sống.

### `app/config.py`
- Class `Settings` kế thừa `pydantic_settings.BaseSettings` — tự động đọc biến môi trường **hoặc** file `.env` (khai báo qua `model_config = SettingsConfigDict(env_file=".env")`).
- 3 cấu hình hiện có:
  - `gemini_api_key`: API key gọi Gemini (**bắt buộc** phải có, nếu không `GeminiService` sẽ raise lỗi khi khởi tạo).
  - `gemini_model`: tên model Gemini dùng để trả lời (mặc định `gemini-1.5-flash`).
  - `cors_origins`: chuỗi các origin frontend được phép gọi API, cách nhau dấu phẩy → property `cors_origins_list` tách thành list.
- `get_settings()` được bọc `@lru_cache` — chỉ đọc `.env` **một lần** cho cả vòng đời app (gọi lại hàm này ở đâu cũng ra cùng 1 instance, không đọc lại file mỗi lần).

### `app/schemas.py`
Định nghĩa "hợp đồng dữ liệu" giữa frontend và backend bằng Pydantic — FastAPI tự validate request/response theo đây và tự sinh docs tại `/docs`.

- `ChatMessage`: 1 tin nhắn trong lịch sử hội thoại — `role` chỉ nhận `"user"` hoặc `"model"` (đúng convention của Gemini SDK), `content` là nội dung text.
- `ChatRequest`: body của `POST /api/chat` — gồm `message` (câu hỏi mới, bắt buộc không rỗng) và `history` (list `ChatMessage`, mặc định rỗng nếu không gửi).
- `ChatResponse`: response trả về — `reply` (câu trả lời từ Gemini) và `disclaimer` (câu cảnh báo y tế cố định, luôn kèm theo mọi câu trả lời).

### `app/routers/chat.py`
- `APIRouter(prefix="/api", tags=["chat"])` — mọi route khai báo trong file này tự có tiền tố `/api`.
- `POST /api/chat`: nhận `ChatRequest`, gọi `get_gemini_service().ask(...)`, bọc kết quả vào `ChatResponse`.
- Bắt lỗi thành 2 nhóm để trả HTTP status code phù hợp:
  - `RuntimeError` (vd. thiếu API key) → **500** — lỗi cấu hình phía server.
  - Exception khác khi gọi Gemini (mạng, quota, key sai...) → **502** — lỗi từ dịch vụ bên ngoài (Bad Gateway).

### `app/services/gemini_service.py`
- `SYSTEM_INSTRUCTION`: prompt hệ thống cố định, quy định "tính cách" và giới hạn an toàn của chatbot — không chẩn đoán bệnh cụ thể, không kê đơn thuốc, khuyến cáo đi khám bác sĩ/gọi 115 khi có dấu hiệu nguy hiểm. Đây là nơi **duy nhất** cần sửa nếu muốn thay đổi cách chatbot "cư xử".
- `GeminiService.__init__`: đọc `Settings`, kiểm tra có `gemini_api_key` chưa (raise `RuntimeError` nếu thiếu — chính là lỗi bạn từng gặp "API key not valid"), rồi cấu hình SDK Gemini và khởi tạo model kèm `system_instruction`.
- `GeminiService.ask(message, history)`: chuyển `history` (list `ChatMessage` theo schema của mình) sang đúng format Gemini SDK cần (`{"role": ..., "parts": [...]}`, rồi mở 1 "phiên chat" (`start_chat`) với lịch sử đó và gửi câu hỏi mới — trả về `response.text`.
- `get_gemini_service()`: pattern singleton đơn giản bằng biến module `_service` — chỉ tạo `GeminiService` (và do đó chỉ đọc `.env`, cấu hình SDK) **một lần**, các lần gọi sau tái sử dụng instance cũ. Nhờ vậy nếu thiếu API key, lỗi chỉ được raise ở lần gọi endpoint đầu tiên (không phải lúc `import`), và service không bị khởi tạo lại mỗi request.

## Vì sao tách theo layer như vậy?

- `schemas.py` tách riêng để 1 nơi duy nhất định nghĩa "hình dạng dữ liệu" — router và service đều import từ đây, tránh lặp lại/không đồng bộ.
- `routers/` tách khỏi `services/`: router chỉ lo HTTP (nhận request, validate, trả response, map lỗi → status code); toàn bộ logic nghiệp vụ (gọi Gemini, xử lý lịch sử chat) nằm trong `services/`. Nếu sau này đổi từ Gemini sang model khác, hoặc thêm bước RAG (truy vấn knowledge base trước khi gọi Gemini — xem `../data-collection/`), chỉ cần sửa/thêm file trong `services/`, không đụng vào router.
