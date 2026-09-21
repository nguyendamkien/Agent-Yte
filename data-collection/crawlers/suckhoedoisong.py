"""Crawler cho Báo Sức khỏe & Đời sống (suckhoedoisong.vn) — cơ quan ngôn luận
chính thức của Bộ Y tế Việt Nam.

Cách tiếp cận: dùng các RSS feed theo chuyên mục mà chính trang này công bố
công khai trong /llms.txt là "phục vụ AI RAG" (xem https://suckhoedoisong.vn/llms.txt),
thay vì cố crawl trang danh mục .htm (render động bằng JS, khó lấy nội dung
tĩnh) hoặc toàn bộ sitemap 18 năm (quá lớn, lẫn nhiều chuyên mục không phải
y tế như Thời sự/Pháp luật).

Cấu trúc trang bài viết dùng schema.org NewsArticle (rất ổn định để parse):
    h1[itemprop=headline]                  -> tiêu đề
    div.detail-sapo[itemprop=description]  -> tóm tắt
    time[itemprop=datePublished][datetime] -> ngày đăng (ISO 8601 có sẵn)
    nav.breadcrumb a[data-role=cate-name]  -> chuyên mục
    div[itemprop=articleBody]              -> nội dung chính, chia đoạn bởi <h2>

⚠️ Yêu cầu trích dẫn của tòa soạn (công bố tại /llms-full.txt): khi dùng dữ
liệu này cho hệ thống AI/RAG, phải ghi rõ nguồn "Theo Báo Sức khỏe & Đời sống"
kèm link gốc. Trường "citation" trong mỗi bản ghi đã dựng sẵn câu này.
"""

import re

from bs4 import BeautifulSoup

from utils import clean_text, fetch_html, make_doc_id, now_iso

BASE_URL = "https://suckhoedoisong.vn"
SOURCE_NAME = "suckhoedoisong"

# Các chuyên mục có nội dung y tế/sức khỏe (bỏ qua Thời sự, Pháp luật, Khỏe-Đẹp
# thẩm mỹ, Truyền hình... vì không phù hợp cho knowledge base hỏi đáp y tế).
CATEGORIES = [
    "/tra-cuu-benh.htm",
    "/y-te/thanh-tuu-y-khoa.htm",
    "/y-te/blog-thay-thuoc.htm",
    "/y-hoc-360/benh-nguoi-cao-tuoi.htm",
    "/y-hoc-360/benh-thuong-gap.htm",
    "/y-hoc-360/benh-phu-nu.htm",
    "/y-hoc-360/benh-nam-gioi.htm",
    "/y-hoc-360/benh-tre-em.htm",
    "/y-hoc-360/suc-khoe-tam-hon.htm",
    "/y-hoc-360/ung-thu.htm",
    "/duoc/an-toan-dung-thuoc.htm",
    "/duoc/thong-tin-duoc-hoc.htm",
    "/duoc/thuoc-moi.htm",
    "/duoc/vaccine.htm",
    "/y-hoc-co-truyen/cay-thuoc-quanh-ta.htm",
    "/y-hoc-co-truyen/chua-benh-khong-dung-thuoc.htm",
    "/dinh-duong/dinh-duong-me-va-be.htm",
    "/dinh-duong/dinh-duong-nguoi-cao-tuoi.htm",
    "/dinh-duong/che-do-an-nguoi-benh.htm",
    "/dinh-duong/canh-giac-thuc-pham.htm",
    "/gioi-tinh/hoi-dap-phong-the.htm",
    "/gioi-tinh/suc-khoe-sinh-san.htm",
    "/gioi-tinh/benh-lay-truyen.htm",
]

ITEM_RE = re.compile(r"<item>(.*?)</item>", re.DOTALL)
LINK_RE = re.compile(r"<link><!\[CDATA\[(.*?)\]\]></link>")


def get_article_urls_from_category(category_path: str) -> list[str]:
    rss_url = BASE_URL + category_path.replace(".htm", ".rss")
    xml = fetch_html(rss_url)
    if not xml:
        return []

    urls = []
    for item_block in ITEM_RE.findall(xml):
        match = LINK_RE.search(item_block)
        if match:
            urls.append(match.group(1).strip())
    return urls


def parse_article_page(url: str) -> dict | None:
    html = fetch_html(url)
    if not html:
        return None

    soup = BeautifulSoup(html, "lxml")

    title_el = soup.select_one("h1[itemprop=headline]") or soup.select_one("h1.detail-title")
    title = clean_text(title_el.get_text()) if title_el else None
    if not title:
        return None

    category_el = soup.select_one("nav.breadcrumb a[data-role=cate-name]")
    category = clean_text(category_el.get_text()) if category_el else "Sức khỏe"

    date_el = soup.select_one("time[itemprop=datePublished]")
    published_date = None
    if date_el and date_el.get("datetime"):
        published_date = date_el["datetime"][:10]  # "2025-08-12T11:40:00+07:00" -> "2025-08-12"

    summary_el = soup.select_one("div.detail-sapo") or soup.select_one("[itemprop=description]")
    summary = clean_text(summary_el.get_text()) if summary_el else ""

    body_el = soup.select_one("[itemprop=articleBody]")
    if not body_el:
        return None

    # Loại bỏ các khối nhiễu: bài liên quan nhúng giữa nội dung, mục lục.
    for noise in body_el.select('div[type="RelatedOneNews"], div.toc-list-headings'):
        noise.decompose()

    sections = []
    current_heading = "Tóm tắt"
    current_parts = [summary] if summary else []

    def flush():
        content = clean_text("\n".join(current_parts))
        if content:
            sections.append({"heading": current_heading, "content": content})

    for child in body_el.children:
        name = getattr(child, "name", None)
        if name in ("h2", "h3"):
            flush()
            current_heading = clean_text(child.get_text())
            current_parts = []
        elif name is not None:
            text = child.get_text("\n")
            if text.strip():
                current_parts.append(text)
    flush()

    if not sections:
        return None

    full_text_parts = [title]
    for section in sections:
        full_text_parts.append(f"## {section['heading']}\n{section['content']}")
    full_text = "\n\n".join(full_text_parts)

    return {
        "id": make_doc_id(SOURCE_NAME, url),
        "source": SOURCE_NAME,
        "url": url,
        "title": title,
        "category": category,
        "published_date": published_date,
        "sections": sections,
        "full_text": full_text,
        "citation": f"Theo Báo Sức khỏe & Đời sống (Cơ quan ngôn luận Bộ Y tế) - {url}",
        "crawled_at": now_iso(),
    }


def run(limit: int | None = None) -> list[dict]:
    """Crawl các chuyên mục y tế của suckhoedoisong.vn qua RSS feed.

    Lưu ý: mỗi chuyên mục RSS chỉ trả về các bài gần đây (thường vài chục bài),
    không phải toàn bộ kho lưu trữ 18 năm của báo. `limit` giới hạn tổng số
    bài (None = không giới hạn, tức lấy hết các bài có trong RSS của mọi
    chuyên mục).
    """
    records = []
    seen_urls = set()

    for category_path in CATEGORIES:
        if limit is not None and len(records) >= limit:
            break

        print(f"[suckhoedoisong] Đang lấy RSS: {category_path}")
        article_urls = get_article_urls_from_category(category_path)
        print(f"  -> {len(article_urls)} bài")

        for url in article_urls:
            if limit is not None and len(records) >= limit:
                break
            if url in seen_urls:
                continue
            seen_urls.add(url)

            print(f"[suckhoedoisong] Đang crawl: {url}")
            record = parse_article_page(url)
            if record:
                records.append(record)
            else:
                print(f"  [!] Không lấy được nội dung: {url}")

    return records
