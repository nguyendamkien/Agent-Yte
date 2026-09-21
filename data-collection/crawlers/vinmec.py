"""Crawler cho mục Tra cứu bệnh của Vinmec (www.vinmec.com).

Cấu trúc:
- Trang danh sách theo chữ cái: /vie/tra-cuu-benh/{a..z}/  -> liệt kê link /vie/benh/{slug}
- Trang chi tiết bệnh dùng tab tĩnh (không cần JS): mỗi tab là
  <div class="item_detial_sick"><h2 class="title_detail_sick">...</h2>
  <div class="body collapsible-target">...</div></div>
"""

import re

from bs4 import BeautifulSoup

from utils import clean_text, fetch_html, make_doc_id, now_iso

BASE_URL = "https://www.vinmec.com"
LETTERS = "abcdefghijklmnopqrstuvwxyz"
SOURCE_NAME = "vinmec"

DISEASE_LINK_RE = re.compile(r"^/vie/benh/[a-z0-9\-]+$")


def get_disease_urls_for_letter(letter: str) -> list[str]:
    html = fetch_html(f"{BASE_URL}/vie/tra-cuu-benh/{letter}/")
    if not html:
        return []

    soup = BeautifulSoup(html, "lxml")
    urls = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if DISEASE_LINK_RE.match(href):
            urls.append(BASE_URL + href)
    # Loại trùng, giữ thứ tự
    return list(dict.fromkeys(urls))


def parse_disease_page(url: str) -> dict | None:
    html = fetch_html(url)
    if not html:
        return None

    soup = BeautifulSoup(html, "lxml")

    title_el = soup.select_one("div.f30.bold.mb2")
    title = clean_text(title_el.get_text()) if title_el else None
    if not title:
        h1 = soup.find("h1")
        title = clean_text(h1.get_text()) if h1 else url

    breadcrumb = [clean_text(a.get_text()) for a in soup.select("a.item-bread")]
    category = breadcrumb[1] if len(breadcrumb) > 1 else "Bệnh"

    sections = []
    for item in soup.select("div.item_detial_sick"):
        heading_el = item.select_one("h2.title_detail_sick")
        body_el = item.select_one("div.body")
        heading = clean_text(heading_el.get_text()) if heading_el else ""
        content = clean_text(body_el.get_text("\n")) if body_el else ""
        if content:
            sections.append({"heading": heading, "content": content})

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
        "published_date": None,
        "sections": sections,
        "full_text": full_text,
        "crawled_at": now_iso(),
    }


def run(limit: int | None = None, letters: str = LETTERS) -> list[dict]:
    """Crawl danh sách bệnh Vinmec. `limit` giới hạn tổng số bài (None = không giới hạn)."""
    records = []
    seen_urls = set()

    for letter in letters:
        if limit is not None and len(records) >= limit:
            break

        print(f"[vinmec] Đang lấy danh sách bệnh chữ '{letter}'...")
        disease_urls = get_disease_urls_for_letter(letter)

        for url in disease_urls:
            if limit is not None and len(records) >= limit:
                break
            if url in seen_urls:
                continue
            seen_urls.add(url)

            print(f"[vinmec] Đang crawl: {url}")
            record = parse_disease_page(url)
            if record:
                records.append(record)
            else:
                print(f"  [!] Không lấy được nội dung: {url}")

    return records
