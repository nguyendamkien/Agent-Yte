# Thu thập dữ liệu y tế tiếng Việt (Data Collection cho RAG)

Bộ script crawl nội dung y tế công khai từ các trang uy tín để làm knowledge
base cho chatbot RAG. **Thư mục này chỉ lo bước thu thập + làm sạch dữ liệu
thô** (ra file `data/*.jsonl`). Việc chunk, embedding và lưu vector DB do
backend đảm nhận — xem mục "Dùng dữ liệu cho RAG" cuối file.

> Thư mục `data/` không nằm trong git (~74 MB, tạo lại được) — cần chạy
> crawler để có dữ liệu.

## Kết quả hiện tại (snapshot)

| Nguồn | Số bài | Dung lượng | Nội dung chính |
|---|---:|---:|---|
| `vinmec.jsonl` | 384 | 7.1 MB | Toàn bộ mục "Tra cứu bệnh" A-Z của Vinmec (100% bệnh có trong danh mục) |
| `medlatec.jsonl` | 800 | 15 MB | 800 bài tin tức y khoa mới nhất của Medlatec |
| `suckhoedoisong.jsonl` | 1122 | 16 MB | Bài gần đây từ 23 chuyên mục y tế của báo Sức khỏe & Đời sống |
| **`combined.jsonl`** | **2306** | **37 MB** | Gộp cả 3 nguồn trên |
| `benh_pho_bien_10.jsonl` | 100 | 1.6 MB | Tập con 10 nhóm bệnh phổ biến, có thêm trường `disease_group` — **backend đang dùng mặc định**. Repo chưa có script tạo lại file này |

Phân bố theo chuyên mục (top):

- **Vinmec**: 100% thuộc chuyên mục "Bệnh" (đúng bản chất — đây là bách khoa tra cứu bệnh).
- **Medlatec**: chủ yếu "Tin tức y khoa" (743), còn lại Dinh dưỡng, Chẩn đoán hình ảnh...
- **Suckhoedoisong**: trải đều Y học 360 (348), Dược (200), Dinh dưỡng (183), Giới tính (150), Y tế (101), Y học cổ truyền (52), Tra cứu bệnh (50)...

Muốn xem số liệu mới nhất, chạy lại:
```bash
python -c "import json,collections; [print(f, sum(1 for _ in open(f, encoding='utf-8'))) for f in ['data/vinmec.jsonl','data/medlatec.jsonl','data/suckhoedoisong.jsonl']]"
```

## Quy trình crawl (pipeline)

Cả 3 crawler dùng chung một kiến trúc 2 bước, nằm trong `crawlers/*.py`:

```
1. Lấy danh sách URL bài viết         2. Với mỗi URL: tải HTML + trích nội dung
   (khác nhau theo từng site)            (chung 1 khuôn: title, category,
                                          published_date, sections[], full_text)
        │                                        │
        ▼                                        ▼
  vinmec.py    : duyệt /vie/tra-cuu-benh/{a..z}/   →  parse tab "Tổng quan/
                 lấy link /vie/benh/{slug}            Nguyên nhân/Triệu chứng..."

  medlatec.py  : đọc sitemap.xml chính thức (16      →  parse breadcrumb + div
                 sitemap con), lọc URL /tin-tuc/         .description, chia theo <h2>

  suckhoedoisong.py : đọc RSS feed của 23 chuyên      →  parse theo schema.org
                 mục y tế (site tự công bố RSS           NewsArticle (itemprop=...),
                 dùng cho AI/RAG trong /llms.txt)         chia theo <h2>/<h3>
```

Sau khi có `sections`, mỗi crawler ghép lại thành `full_text` (title + từng
mục nối bằng tiêu đề `## `), rồi cả 3 file `.jsonl` được gộp thủ công bằng
`cat vinmec.jsonl medlatec.jsonl suckhoedoisong.jsonl > combined.jsonl` (hoặc
tự động nếu chạy `run_crawl.py --source all`).

Tiện ích dùng chung (`utils.py`):
- `fetch_html()`: gọi HTTP có **rate-limit** (mặc định 1.5s/request), tự
  **retry** khi lỗi mạng, tự sửa lỗi encoding khi server không khai báo
  charset (gặp ở suckhoedoisong.vn — response bị hiểu nhầm là ISO-8859-1).
- `clean_text()`: chuẩn hóa khoảng trắng/xuống dòng sau khi tách chữ từ HTML.
- `make_doc_id()`: sinh id ổn định từ hash URL (`<source>-<sha1[:10]>`).
- `save_jsonl()`: ghi danh sách dict ra file JSONL.

Trước khi viết từng crawler, mình đã tải thử HTML/RSS thật của mỗi trang để
soi đúng class/thẻ cần lấy (không đoán mò) — các file `scratch_*.html/.txt`
tạo ra trong lúc khảo sát đó **chỉ là tài liệu tạm thời, đã xóa hết**, không
phải một phần của dự án và không cần giữ lại.

## Nguồn dữ liệu & cơ sở pháp lý

| Nguồn | robots.txt | Ghi chú |
|---|---|---|
| [vinmec.com](https://www.vinmec.com) — mục Tra cứu bệnh | Cho phép crawl nội dung công khai (chỉ chặn `/wp-admin/`, trang đăng nhập/đăng ký) | Không có sitemap khai báo, crawler tự duyệt theo danh mục A-Z |
| [medlatec.vn](https://medlatec.vn) — mục Tin tức y khoa | **Cho phép rõ ràng** các bot AI (ClaudeBot, GPTBot, Google-Extended...) và bot thường, chỉ chặn các trang quản trị/tài khoản | Có sitemap.xml chính thức |
| [suckhoedoisong.vn](https://suckhoedoisong.vn) — **cơ quan ngôn luận chính thức của Bộ Y tế** | Cho phép toàn bộ (`Allow: /`), chỉ chặn trang tìm kiếm | Trang này **tự công bố `/llms.txt` và `/llms-full.txt`** hướng dẫn AI/RAG dùng RSS feed theo chuyên mục — crawler dùng đúng kênh họ khuyến nghị |

Đã kiểm tra `robots.txt` của cả ba trang trước khi viết crawler (xem bảng
trên). Tuy vậy:

- Nội dung các trang này **có bản quyền** (thuộc Vinmec/MEDLATEC/Báo Sức khỏe
  & Đời sống). Việc crawl ở đây phục vụ mục đích **học tập/thử nghiệm cá
  nhân** (xây dựng knowledge base cho một chatbot RAG demo). Nếu bạn định
  dùng dữ liệu này cho sản phẩm thương mại/công khai, nên liên hệ xin phép
  chủ sở hữu nội dung trước.
- **suckhoedoisong.vn yêu cầu trích dẫn bắt buộc** khi dùng dữ liệu cho
  AI/RAG (công bố tại `/llms-full.txt`): phải ghi "Theo Báo Sức khỏe & Đời
  sống" kèm link gốc khi chatbot trả lời dựa trên nguồn này. Mỗi bản ghi của
  nguồn này đã có sẵn trường `citation` đúng định dạng yêu cầu — **khi build
  RAG, nhớ hiển thị trường này trong câu trả lời của chatbot**, đừng bỏ qua.
- Crawler tự giới hạn tốc độ (mặc định 1.5s/request), có User-Agent định danh
  rõ ràng (không giả mạo trình duyệt) để chủ site có thể nhận diện.
- Luôn dùng tham số `--limit` khi test để tránh tải không cần thiết lên
  server của họ.

## Cài đặt

Yêu cầu Python 3.11+.

```bash
cd data-collection
python -m venv venv
venv\Scripts\activate        # Windows; macOS/Linux: source venv/bin/activate
pip install -r requirements.txt
```

## Sử dụng

```bash
# Test nhanh, mỗi nguồn 10 bài
python run_crawl.py --source all --limit 10

# Crawl lại toàn bộ mục tra cứu bệnh Vinmec (~384 bệnh, ~10 phút)
python run_crawl.py --source vinmec --limit 0

# Chỉ crawl vài chữ cái đầu để test
python run_crawl.py --source vinmec --limit 20 --letters abc

# Crawl thêm Medlatec (vd. tăng lên 1500 bài — sitemap còn nhiều hơn 800 đã lấy)
python run_crawl.py --source medlatec --limit 1500

# Crawl lại Báo Sức khỏe & Đời sống (23 chuyên mục, mỗi mục ~50 bài gần nhất)
python run_crawl.py --source suckhoedoisong --limit 0
```

> `--limit 0` nghĩa là **không giới hạn**. Với Vinmec/suckhoedoisong việc này
> vẫn có giới hạn tự nhiên (Vinmec hết bệnh trong danh mục ở ~384 bài;
> suckhoedoisong hết bài trong RSS ở ~1100 bài). Với Medlatec thì **không có
> giới hạn tự nhiên** (sitemap còn hàng chục nghìn URL lịch sử) nên **luôn
> đặt `--limit` cụ thể**, đừng dùng `0` để tránh crawl nhiều giờ liền.

Chạy lại một nguồn sẽ **ghi đè** file `.jsonl` tương ứng (không cộng dồn).
Sau khi crawl xong, gộp lại bằng:
```bash
cat data/vinmec.jsonl data/medlatec.jsonl data/suckhoedoisong.jsonl > data/combined.jsonl
```
(hoặc tự động nếu chạy `python run_crawl.py --source all`).

## Schema dữ liệu (mỗi dòng JSONL là 1 tài liệu)

```json
{
  "id": "vinmec-8d330cc117",
  "source": "vinmec",
  "url": "https://www.vinmec.com/vie/benh/...",
  "title": "Tên bệnh: Nguyên nhân, triệu chứng...",
  "category": "Bệnh",
  "published_date": "2023-06-21",
  "sections": [
    {"heading": "Tổng quan bệnh ...", "content": "..."},
    {"heading": "Nguyên nhân bệnh ...", "content": "..."}
  ],
  "full_text": "Toàn bộ nội dung đã ghép (title + các section, đánh dấu \"## \")",
  "citation": "(chỉ có ở nguồn suckhoedoisong) Theo Báo Sức khỏe & Đời sống - <url>",
  "crawled_at": "2026-09-13T16:10:32+00:00"
}
```

`full_text` là trường tiện dùng nhất cho bước chunk + embedding sau này;
`sections` giữ cấu trúc gốc nếu bạn muốn chunk theo từng mục.

## Các điểm cần biết khi dùng cho bước RAG tiếp theo

- **Vinmec**: cuối một số mục (vd. "Các biện pháp điều trị") có kèm danh sách
  "Xem thêm: ..." — là tiêu đề bài viết liên quan, không phải nội dung chính.
  Có thể coi là nhiễu nhỏ, cân nhắc lọc thêm khi chunk.
- **Medlatec**: sitemap của họ có lẫn một số URL cũ đã gỡ bài (trả về 404) —
  crawler tự động bỏ qua, không phải lỗi (~5% trong lần crawl gần nhất). Code
  đã tự loại các chuyên mục không phải nội dung y tế (tin nội bộ, tuyển
  dụng...), nhưng một vài mục ngoài lề (vd. "Chương trình khuyến mại") vẫn
  lọt qua với số lượng nhỏ — có thể lọc thêm theo `category` khi chunk nếu
  muốn sạch tuyệt đối.
- **suckhoedoisong.vn**: dùng RSS theo chuyên mục nên chỉ lấy được các bài
  **gần đây** (RSS mỗi chuyên mục giới hạn ~50 bài mới nhất), không phải toàn
  bộ kho lưu trữ 18 năm của báo (site có sitemap tĩnh
  `/StaticSitemaps/sitemaps-YYYY-M-D1-D2.xml` cho việc đó, nhưng dung lượng
  rất lớn và lẫn nhiều chuyên mục ngoài y tế — không triển khai trong phạm vi
  này, có thể làm thêm nếu cần crawl sâu theo mốc thời gian cụ thể). Vì
  breadcrumb category là category "chính" của bài (có thể khác chuyên mục RSS
  đã tìm ra nó), thực tế vẫn lọt vào ~30 bài thuộc "Thời sự"/"Sức khỏe
  TV"/"Thị trường" — nên lọc `category` không nằm trong danh sách y tế nếu
  cần dữ liệu sạch tuyệt đối. Một số bài dạng hỏi-đáp trình bày câu hỏi phụ
  bằng chữ đậm thay vì thẻ heading thật, khiến việc tách `sections` không
  hoàn hảo ở vài bài (nội dung không mất, chỉ gộp nhãn mục) — `full_text`
  vẫn đầy đủ nên không ảnh hưởng nếu bạn chunk theo `full_text` thay vì theo
  `sections`.
- Dữ liệu **chưa được chunk** theo kích thước token cố định — bước này nên
  làm ở giai đoạn xây embedding (tùy mô hình embedding bạn chọn sẽ có
  max-token khác nhau).
- Có thể mở rộng thêm nguồn bằng cách tạo file mới trong `crawlers/` theo
  cùng pattern (`run(limit)` trả về list dict theo đúng schema trên).

## Dùng dữ liệu cho RAG

Backend đã có sẵn pipeline RAG đọc trực tiếp file trong `data/` — mặc định
`data/benh_pho_bien_10.jsonl`, đổi qua `DATA_PATH` trong `backend/.env` (vd
`../data-collection/data/combined.jsonl` để dùng toàn bộ 2.306 bài):

- chunk theo `sections` (mục dài được tách tiếp theo câu, có overlap);
- tạo embedding bằng OpenAI `text-embedding-3-small` và lưu vào ChromaDB;
- khi chat, tìm các đoạn liên quan bằng hybrid search (BM25 + vector, gộp RRF)
  rồi mới gọi Gemini sinh câu trả lời, kèm nguồn (`url`, `citation`) trả về
  cho frontend.

Chi tiết pipeline: [../docs/RAG.md](../docs/RAG.md).

Sau khi crawl xong, tạo index bằng:

```bash
cd ../backend
python -m app.scripts.ingest
```

Xem hướng dẫn đầy đủ ở [README gốc](../README.md).
