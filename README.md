# ChatBot Y Tế

Chatbot hỏi đáp thông tin y tế đơn giản, gồm:

- **backend/**: FastAPI, gọi Google Gemini API để trả lời câu hỏi.
- **frontend/**: ReactJS (Vite), giao diện chat.
- **data-collection/**: script thu thập dữ liệu y tế tiếng Việt (Vinmec,
  Medlatec) làm knowledge base cho bước RAG sau này — xem
  [data-collection/README.md](data-collection/README.md).

> ⚠️ Đây là công cụ tham khảo thông tin, **không thay thế** chẩn đoán/tư vấn
> của bác sĩ hay chuyên gia y tế.

## 1. Chạy Backend (FastAPI)

```bash
cd backend
python -m venv venv
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

pip install -r requirements.txt

# Tạo file cấu hình từ mẫu, rồi điền GEMINI_API_KEY của bạn
copy .env.example .env      # Windows
# cp .env.example .env      # macOS/Linux

uvicorn main:app --reload --port 8000
```

Backend chạy tại: http://localhost:8000
Xem tài liệu API tự động (Swagger UI): http://localhost:8000/docs

Lấy Gemini API key miễn phí tại: https://aistudio.google.com/apikey

## 2. Chạy Frontend (ReactJS)

```bash
cd frontend
npm install

# (tuỳ chọn) copy .env.example .env nếu backend không chạy ở localhost:8000
copy .env.example .env

npm run dev
```

Frontend chạy tại: http://localhost:5173

## 3. Cấu trúc thư mục

```
ChatBot_Yte/
├── backend/
│   ├── app/
│   │   ├── config.py          # Đọc cấu hình từ .env
│   │   ├── schemas.py         # Pydantic models cho request/response
│   │   ├── routers/chat.py    # Endpoint POST /api/chat
│   │   └── services/gemini_service.py  # Gọi Gemini API
│   ├── main.py                # Khởi tạo FastAPI app + CORS
│   ├── requirements.txt
│   └── .env.example
└── frontend/
    ├── src/
    │   ├── api/chatApi.js         # Gọi API backend
    │   ├── components/
    │   │   ├── MessageBubble.jsx
    │   │   └── ChatInput.jsx
    │   ├── App.jsx                # Giao diện chat chính
    │   └── App.css
    └── .env.example
```

## 4. Ghi chú

- Backend giữ system prompt yêu cầu Gemini không chẩn đoán bệnh cụ thể, không
  kê đơn thuốc, và khuyến cáo đi khám bác sĩ / gọi cấp cứu 115 khi cần.
- Lịch sử hội thoại được frontend gửi kèm mỗi request để chatbot nhớ ngữ cảnh
  (không lưu trữ phía server).
- Muốn đổi model Gemini (vd. `gemini-1.5-pro`), sửa biến `GEMINI_MODEL` trong
  file `backend/.env`.
