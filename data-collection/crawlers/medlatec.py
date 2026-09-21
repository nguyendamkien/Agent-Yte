"""Crawler cho tin tức y khoa của Medlatec (medlatec.vn).

Cấu trúc:
- Sitemap index: https://medlatec.vn/sitemap.xml -> 16 sitemap con
- Mỗi sitemap con chứa nhiều <loc>, lọc lấy URL dạng /tin-tuc/{slug}
- Trang bài viết:
    h1.page-title            -> tiêu đề
    div.date                 -> "Ngày DD/MM/YYYY"
    ol.breadcrumb li a       -> breadcrumb, mục thứ 2 là chuyên mục
    div.shortdescription     -> tóm tắt
    div.description          -> nội dung chính, chia đoạn bởi các thẻ <h2>
"""

import re

from bs4 import BeautifulSoup

from utils import clean_text, fetch_html, make_doc_id, now_iso

BASE_URL = "https://medlatec.vn"
SITEMAP_INDEX_URL = f"{BASE_URL}/sitemap.xml"
SOURCE_NAME = "medlatec"

ARTICLE_URL_RE = re.compile(r"^https://medlatec\.vn/tin-tuc/[a-z0-9\-]+$")
DATE_RE = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})")

# Các chuyên mục không phải nội dung y tế (tin nội bộ, tuyển dụng...) -> bỏ qua.
EXCLUDED_CATEGORIES = {
    "Hoạt động nội bộ",
    "Tuyển dụng",
    "Thông báo",
    "Sự kiện",
    "Tin tức MEDLATEC",
}


def get_sub_sitemap_urls() -> list[str]:
    xml = fetch_html(SITEMAP_INDEX_URL)
    if not xml:
        return []
    soup = BeautifulSoup(xml, "xml")
    return [loc.get_text().strip() for loc in soup.find_all("loc")]


def get_article_urls_from_sitemap(sitemap_url: str) -> list[str]:
    xml = fetch_html(sitemap_url)
    if not xml:
        return []
    soup = BeautifulSoup(xml, "xml")
    urls = [loc.get_text().strip() for loc in soup.find_all("loc")]
    return [u for u in urls if ARTICLE_URL_RE.match(u)]


def _parse_date(text: str) -> str | None:
    match = DATE_RE.search(text)
    if not match:
        return None
    day, month, year = match.groups()
    return f"{year}-{int(month):02d}-{int(day):02d}"


def _split_sections(description_el) -> list[dict]:
    sections = []
    current_heading = "Nội dung"
    current_parts: list[str] = []

    def flush():
        content = clean_text("\n".join(current_parts))
        if content:
            sections.append({"heading": current_heading, "content": content})

    for child in description_el.children:
        name = getattr(child, "name", None)
        if name == "h2":
            flush()
            current_heading = clean_text(child.get_text())
            current_parts = []
        elif name is not None:
            text = child.get_text("\n")
            if text.strip():
                current_parts.append(text)

    flush()
    return sections


def parse_article_page(url: str) -> dict | None:
    html = fetch_html(url)
    if not html:
        return None

    soup = BeautifulSoup(html, "lxml")

    title_el = soup.select_one("h1.page-title")
    title = clean_text(title_el.get_text()) if title_el else url

    breadcrumb = [clean_text(a.get_text()) for a in soup.select("ol.breadcrumb a")]
    category = breadcrumb[1] if len(breadcrumb) > 1 else "Tin tức y khoa"
    if category in EXCLUDED_CATEGORIES:
        return None

    date_el = soup.select_one("div.date")
    published_date = _parse_date(date_el.get_text()) if date_el else None

    summary_el = soup.select_one("div.shortdescription")
    summary = clean_text(summary_el.get_text()) if summary_el else ""

    description_el = soup.select_one("div.description")
    if not description_el:
        return None
    sections = _split_sections(description_el)
    if summary:
        sections.insert(0, {"heading": "Tóm tắt", "content": summary})

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
        "crawled_at": now_iso(),
    }


def run(limit: int | None = None) -> list[dict]:
    """Crawl tin tức y khoa Medlatec. `limit` giới hạn tổng số bài (None = không giới hạn)."""
    records = []

    print("[medlatec] Đang lấy danh sách sitemap con...")
    sub_sitemaps = get_sub_sitemap_urls()
    print(f"[medlatec] Tìm thấy {len(sub_sitemaps)} sitemap con.")

    for sitemap_url in sub_sitemaps:
        if limit is not None and len(records) >= limit:
            break

        print(f"[medlatec] Đang đọc {sitemap_url}...")
        article_urls = get_article_urls_from_sitemap(sitemap_url)
        print(f"  -> {len(article_urls)} bài viết /tin-tuc/")

        for url in article_urls:
            if limit is not None and len(records) >= limit:
                break

            print(f"[medlatec] Đang crawl: {url}")
            record = parse_article_page(url)
            if record:
                records.append(record)
            else:
                print(f"  [!] Không lấy được nội dung: {url}")

    return records
