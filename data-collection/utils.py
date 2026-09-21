"""Tiện ích dùng chung: gọi HTTP lịch sự (rate-limit, retry), làm sạch text, lưu JSONL."""

import hashlib
import json
import re
import time
from datetime import datetime, timezone

import requests

from config import (
    BACKOFF_BASE_SECONDS,
    MAX_RETRIES,
    REQUEST_DELAY_SECONDS,
    REQUEST_TIMEOUT,
    USER_AGENT,
)

_session = requests.Session()
_session.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "vi-VN,vi;q=0.9"})

_last_request_time = 0.0


def fetch_html(url: str) -> str | None:
    """Tải HTML của một URL, tự động rate-limit + retry. Trả về None nếu thất bại."""
    global _last_request_time

    for attempt in range(1, MAX_RETRIES + 1):
        elapsed = time.monotonic() - _last_request_time
        if elapsed < REQUEST_DELAY_SECONDS:
            time.sleep(REQUEST_DELAY_SECONDS - elapsed)

        try:
            response = _session.get(url, timeout=REQUEST_TIMEOUT)
            _last_request_time = time.monotonic()

            if response.status_code == 200:
                # Một số server (vd. suckhoedoisong.vn) không khai báo charset
                # trong header Content-Type, khiến requests mặc định hiểu
                # nhầm là ISO-8859-1 -> vỡ chữ tiếng Việt. Ép về encoding
                # thực tế của nội dung (apparent_encoding) trong trường hợp đó.
                if response.encoding is None or response.encoding.lower() in (
                    "iso-8859-1",
                    "ascii",
                ):
                    response.encoding = response.apparent_encoding
                return response.text
            if response.status_code == 404:
                return None
            print(f"  [!] HTTP {response.status_code} khi tải {url} (lần {attempt})")
        except requests.RequestException as exc:
            print(f"  [!] Lỗi mạng khi tải {url} (lần {attempt}): {exc}")

        if attempt < MAX_RETRIES:
            time.sleep(BACKOFF_BASE_SECONDS * attempt)

    print(f"  [x] Bỏ qua sau {MAX_RETRIES} lần thử: {url}")
    return None


WHITESPACE_RE = re.compile(r"[ \t]+")
MULTI_NEWLINE_RE = re.compile(r"\n{3,}")


def clean_text(text: str) -> str:
    """Chuẩn hóa khoảng trắng trong text đã tách từ HTML."""
    text = text.replace("\xa0", " ")
    text = WHITESPACE_RE.sub(" ", text)
    text = "\n".join(line.strip() for line in text.split("\n"))
    text = MULTI_NEWLINE_RE.sub("\n\n", text)
    return text.strip()


def make_doc_id(source: str, url: str) -> str:
    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:10]
    return f"{source}-{digest}"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def save_jsonl(records: list[dict], path) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    print(f"Đã lưu {len(records)} tài liệu vào {path}")
