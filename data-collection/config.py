"""Cấu hình chung cho các crawler thu thập dữ liệu y tế tiếng Việt."""

from pathlib import Path

# Định danh crawler một cách minh bạch (không giả mạo trình duyệt), để chủ
# website có thể nhận diện và liên hệ nếu cần.
USER_AGENT = (
    "ChatBotYTeCrawler/1.0 "
    "(+Thu thap noi dung y te cong khai cho du an chatbot ca nhan/hoc thuat; "
    "tuan thu robots.txt)"
)

REQUEST_TIMEOUT = 15  # giây
REQUEST_DELAY_SECONDS = 1.5  # nghỉ giữa các request để không gây tải cho server
MAX_RETRIES = 3
BACKOFF_BASE_SECONDS = 2

DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)
