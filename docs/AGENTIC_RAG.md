# Agentic RAG — kế hoạch chuyển chatbot thành agent

> **Trạng thái:** bước 3 đã làm ở tầng retriever (13/10/2026); bước 1, 2, 4 còn là thiết kế. Tài liệu mô tả 4 bước đầu để chuyển pipeline RAG cố định hiện tại sang agent tự quyết định việc tìm tài liệu, và các tool agent sẽ dùng. Pipeline hiện tại: xem [RAG.md](RAG.md); cách đo: xem [RAG_EVAL.md](RAG_EVAL.md).

## Khác gì so với hiện tại

Hiện tại mỗi câu hỏi đi qua đúng một đường, do code quyết định (`RagService.ask_stream`):

```
câu hỏi ─► viết lại câu hỏi (nếu có lịch sử) ─► tìm 1 lần ─► Gemini trả lời
```

Với agent, Gemini quyết định ở mỗi vòng: tìm tiếp hay trả lời.

```
câu hỏi + lịch sử ─► Gemini ─┬─► gọi tool ─► code chạy tool ─► trả kết quả cho Gemini ─┐
                      ▲      │                                                        │
                      └──────┼────────────────────────────────────────────────────────┘
                             └─► trả lời (stream về frontend)
```

| Tình huống | Hiện tại | Agent |
|---|---|---|
| Câu cần nhiều bài ("Tăng huyết áp ảnh hưởng tim và thận thế nào?") | 1 truy vấn, 5 chunk chia cho cả hai ý. `multi-01` faithfulness 0.67 | Tìm riêng từng ý |
| Câu nối tiếp ("Vậy điều trị thế nào?") | Thêm 1 lần gọi Gemini để viết lại; đôi khi trả về rỗng (`follow-02`) | Model tự viết truy vấn khi gọi tool, bỏ được bước viết lại |
| Chào hỏi, câu ngoài lĩnh vực | Vẫn tìm và rerank (~12 s) rồi mới từ chối | Trả lời ngay, không tìm |
| Lần tìm đầu chưa đủ | Trả lời với những gì có | Tìm lại bằng truy vấn khác, hoặc đọc cả bài |

Cái giá: agent tự do hơn nên khó kiểm soát hơn (thời gian, số lần gọi, tuân thủ quy tắc an toàn). Bước 2 và bước 4 tồn tại để xử lý chuyện đó.

## Các tool

Agent có 2 tool. Cả hai chỉ đọc dữ liệu đã có trong Chroma, không gọi ra ngoài.

### `search_medical_docs` — bước 1, mở rộng ở bước 3

Bọc `Retriever.search` hiện có (hybrid BM25 + dense, RRF, rerank, ngưỡng "không có tài liệu").

| Tham số | Kiểu | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `query` | string | có | Câu truy vấn **độc lập, đủ ý**, có tên bệnh / thuốc / thực phẩm. Model tự viết từ câu hỏi và lịch sử |
| `disease_group` | enum | không | Chỉ tìm trong một nhóm bệnh. Thêm ở bước 3 |

Kết quả trả cho model: tối đa `RAG_TOP_K` chunk, cùng định dạng mà `build_context` đang dùng, thêm `document_id` để gọi được tool thứ hai:

```
[Nguồn 2] Bệnh gout: Nguyên nhân, triệu chứng… | Mục: Điều trị | document_id: vinmec-ab12cd34ef
Nội dung: …
URL: https://…
```

Khi retriever trả về rỗng (dưới ngưỡng `RERANK_MIN_SCORE`), kết quả là một dòng cố định: `Không có tài liệu phù hợp với truy vấn này.` — không kèm chunk nào.

### `get_article` — bước 3

Đọc nguyên một bài, hoặc một mục của bài, khi chunk tìm được bị cắt giữa chừng hoặc câu trả lời nằm ở mục khác của cùng bài.

| Tham số | Kiểu | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `document_id` | string | có | Lấy từ kết quả của `search_medical_docs`. Model không được tự đặt |
| `section` | string | không | Tên mục (vd "Điều trị"). Bỏ trống thì trả cả bài |

Bài dài trung vị ~5.700 ký tự, dài nhất ~14.000 ký tự. Tool cắt ở 8.000 ký tự và ghi rõ "(đã cắt, gọi lại với `section` để đọc phần còn lại)", kèm danh sách tên mục của bài.

Tool này không cần embedding hay rerank nên gần như tức thì — rẻ hơn nhiều so với tìm lần nữa.

### Không làm thành tool

- **Viết lại câu hỏi:** thành tham số `query` của tool tìm kiếm.
- **Danh sách nhóm bệnh:** đưa thẳng vào `enum` của tham số `disease_group`, không cần tool riêng để hỏi.
- **Hỏi lại người dùng:** là một kiểu câu trả lời, không phải tool. Nằm ngoài 4 bước này.

## Bước 1 — Vòng lặp agent với function calling

**Mục tiêu:** Gemini tự gọi `search_medical_docs`, 0 đến nhiều lần, rồi trả lời. Chưa đổi gì ở retrieval.

### Vòng lặp

1. Gửi cho Gemini: lịch sử (đã cắt theo `HISTORY_MAX_TURNS`) + câu hỏi gốc, kèm khai báo tool.
2. Nếu Gemini trả về lời gọi tool: code chạy tool, gửi kết quả lại, quay về đầu bước 2.
3. Nếu Gemini trả về text: đó là câu trả lời, stream về frontend.
4. Đã gọi đủ `AGENT_MAX_TOOL_CALLS` lần (đề xuất 3): lần gọi Gemini kế tiếp tắt tool, buộc phải trả lời bằng những gì đã có.

SDK đang dùng (`google-generativeai` 0.8.3) có sẵn function calling: khai báo `tools=[…]` khi tạo `GenerativeModel`. Viết vòng lặp bằng tay thay vì dùng chế độ tự động của SDK, vì cần chèn sự kiện SSE và đếm số lần gọi giữa các vòng.

### Việc code phải giữ, không giao cho model

- **Đánh số nguồn xuyên suốt một request.** `[Nguồn i]` phải khớp với danh sách nguồn hiển thị ở frontend. Giữ một bảng `source_key → số` cho cả request; chunk của lần tìm thứ hai thuộc bài đã gặp thì dùng lại số cũ, bài mới thì đánh số tiếp. `collect_sources` chạy trên toàn bộ chunk đã lấy, theo đúng thứ tự đó.
- **Không gửi lại chunk trùng.** Lần tìm sau bỏ các chunk đã trả ở lần trước, để model không tốn token đọc lại.
- **Chặn `document_id` lạ** (bước 3): chỉ nhận id đã xuất hiện trong kết quả tìm kiếm của request này.

### Quy tắc trả lời chuyển từ prompt sang system instruction

Hiện các quy tắc bám tài liệu nằm trong `build_rag_prompt` và `build_no_context_prompt`, ghép vào **mỗi câu hỏi**. Với agent không còn một prompt ghép sẵn, nên chúng chuyển vào `SYSTEM_INSTRUCTION`:

- Mọi thông tin y tế trong câu trả lời phải lấy từ kết quả tool; chưa tìm thì không được khẳng định điều gì về bệnh, thuốc, điều trị.
- Tool trả về "không có tài liệu" cho mọi truy vấn: nói chưa có thông tin, tối đa 3 câu, không nêu triệu chứng / con số / thuốc / tiên lượng (giữ nguyên nội dung `build_no_context_prompt`).
- Không nêu liều thuốc kể cả khi tài liệu có ghi (giữ nguyên quy tắc ngày 09/10).
- Dấu hiệu cấp cứu: khuyên gọi 115 **ngay ở câu đầu**, không chờ tìm xong.
- Câu ngoài lĩnh vực sức khỏe, lời chào: trả lời luôn, không gọi tool.
- Khi nào nên tìm nhiều lần: câu hỏi có nhiều ý / nhiều bệnh, hoặc kết quả đầu chưa trả lời được câu hỏi.

**Rủi ro lớn nhất của bước này:** hiện việc "không có chunk thì không được kể thêm" do code bảo đảm (không có chunk → dùng prompt riêng). Sau bước 1 nó chỉ còn là một quy tắc trong system instruction, và model có thể trả lời từ kiến thức riêng mà không gọi tool. Cần đo kỹ ở bước 4. Nếu đo thấy còn lọt, thêm chốt chặn bằng code: request kết thúc mà không có chunk nào được lấy về thì sinh lại câu trả lời bằng `build_no_context_prompt`.

### Sự kiện SSE

Giữ nguyên định dạng của `/api/chat/stream`, chỉ đổi nội dung:

| Sự kiện | Thay đổi |
|---|---|
| `status` | Bỏ `rewriting`. `retrieving` phát mỗi lần gọi tool, kèm truy vấn: `{"stage": "retrieving", "query": "điều trị gout"}` |
| `sources` | Phát lại sau **mỗi** lần gọi tool, mỗi lần là danh sách đầy đủ tính đến lúc đó. Frontend đang ghi đè cả danh sách khi nhận sự kiện này nên không phải sửa |
| `delta`, `done`, `error` | Không đổi |

Frontend chỉ cần sửa nếu muốn hiển thị truy vấn đang tìm.

### Lịch sử

Frontend chỉ lưu text câu hỏi và câu trả lời, không lưu lời gọi tool. Sang câu hỏi sau, model thấy câu trả lời cũ nhưng không thấy các chunk cũ, nên sẽ tìm lại nếu cần. Chấp nhận ở bước này.

### File thay đổi

| File | Thay đổi |
|---|---|
| `app/services/gemini_service.py` | Khai báo tool, system instruction mới, hàm chạy một vòng (trả về lời gọi tool hoặc stream text) |
| `app/services/agent_service.py` *(mới)* | Vòng lặp, bảng đánh số nguồn, giới hạn số lần gọi, phát sự kiện SSE |
| `app/rag/tools.py` *(mới)* | Hàm thực thi từng tool và định dạng kết quả |
| `app/routers/chat.py` | Chọn `AgentService` hoặc `RagService` theo cấu hình |
| `app/config.py`, `.env.example` | `AGENT_ENABLED` (mặc định `false` cho tới khi qua bước 4), `AGENT_MAX_TOOL_CALLS=3` |

`RagService` giữ nguyên, để so sánh hai pipeline trên cùng golden set và để quay lại được.

**Xong khi:** hỏi `multi-01` thấy 2 lần gọi tool với 2 truy vấn khác nhau; hỏi "xin chào" không có lần gọi nào; số `[Nguồn i]` trong câu trả lời khớp danh sách nguồn.

## Bước 2 — Giữ thời gian trả lời chấp nhận được

**Vấn đề:** rerank mất ~11,5 s cho mỗi lần tìm (10 ứng viên × tối đa 1.024 token, ~0,8 s cho mỗi 512 token, CPU 8 nhân). Agent tìm 3 lần là ~35 s chỉ riêng rerank.

Thử theo thứ tự, từ rẻ đến đắt, đo lại bằng `eval_retrieval.py` sau mỗi thay đổi:

1. **Ngân sách rerank cho cả request.** Lần tìm đầu rerank 10 ứng viên như hiện tại; từ lần thứ hai chỉ 5. Tối đa 20 cặp cho một request thay vì 30.
2. **Giảm `MAX_LENGTH` của reranker từ 1.024 xuống 512 token.** Thời gian gần như tỉ lệ với độ dài, nên có thể nhanh gấp đôi. Chunk dài nhất ~1.800 token nên phần đuôi bị cắt nhiều hơn — phải đo xem hit@1 và ngưỡng 0,4 còn giữ được không.
3. **Không tính lại cặp đã chấm.** Lưu điểm theo (truy vấn, chunk) trong request; lợi ít, nhưng gần như không tốn công.
4. **GPU.** Nếu deploy lên máy có GPU thì vấn đề này gần như biến mất; ghi lại như một lựa chọn, không làm trong bước này.

Ngoài ra bước 1 đã tự tiết kiệm ở hai chỗ: câu không cần tìm bớt ~12 s, và câu nối tiếp bớt ~1 s viết lại.

**Xong khi** (đo trên golden set, một người dùng, CPU hiện tại):

| Loại câu | Hiện tại | Mục tiêu |
|---|---|---|
| Câu một ý (factual, specific) | ~12–13 s + Gemini | Không chậm hơn |
| Câu nhiều ý (multi_doc) | ~12–13 s + Gemini | ≤ 25 s |
| Chào hỏi, off-topic | ~12–13 s + Gemini | < 3 s |

Chất lượng retrieval không được giảm quá mức dao động của bộ test (1–2 câu trên 70).

## Bước 3 — Metadata và tool thứ hai

> **Đã làm ngày 13/10/2026** (mục 1–4, và phần retriever của mục 5–6): `disease_group` trong metadata, tên bài trong text chunk, ingest lại, `Retriever.search(..., disease_group=...)`, `Retriever.disease_groups`, `Retriever.get_article(document_id)`. Kết quả đo: mục "Đưa tên bài vào text chunk" trong [RAG_EVAL.md](RAG_EVAL.md).
> **Còn lại, làm cùng bước 1:** khai báo hai tool cho Gemini và phần bọc kết quả (cắt bài ở 8.000 ký tự, chọn theo `section`, chặn `document_id` lạ).

**Mục tiêu:** sửa hai hạn chế đã ghi trong [RAG.md](RAG.md), nhờ đó tool tìm kiếm lọc được theo bệnh, và thêm `get_article`.

1. **Đưa `disease_group` vào metadata.** File dữ liệu đã có sẵn trường này cho cả 100 bài (10 nhóm, từ 3 đến 17 bài mỗi nhóm); chỉ cần thêm một dòng trong `chunker.py`.
2. **Đưa `title` vào text chunk**: `"{title}\n{heading}\n{nội dung}"` thay cho `"{heading}\n{nội dung}"`. Hiện 77/428 section có heading chung là "Tóm tắt", nên chunk không mang tên bệnh và dễ bị lấy nhầm giữa các bệnh gần nhau.
3. **Chạy lại ingest** (~1 phút, ~$0,006), khởi động lại server để dựng lại BM25.
4. **Đo lại retrieval trước khi làm tiếp.** Thay đổi ở mục 2 đổi cả embedding lẫn BM25 của mọi chunk; ngưỡng `RERANK_MIN_SCORE = 0.4` được chọn theo phân bố điểm cũ nên phải kiểm tra lại.
5. **Thêm tham số `disease_group` cho `search_medical_docs`.** Nhánh dense lọc bằng `where` của Chroma; nhánh BM25 lọc theo metadata sau khi chấm điểm. Danh sách `enum` lấy từ metadata trong index lúc khởi động, không viết cứng — để khi đổi sang `combined.jsonl` không phải sửa code.
6. **Thêm tool `get_article`.** `Retriever` đã giữ toàn bộ chunk trong RAM (`_chunks`) cho BM25; gom theo `document_id` và sắp theo số thứ tự chunk là có lại bài viết, không cần đọc file JSONL.

Lưu ý với mục 5: lọc theo nhóm bệnh là **tuỳ chọn** của model. Câu về hai bệnh ("viêm gan A khác viêm gan B thế nào", trong khi dữ liệu chỉ có nhóm Viêm gan B) mà lọc sai nhóm thì mất kết quả đúng. Mô tả tool phải ghi rõ: chỉ dùng khi chắc chắn câu hỏi thuộc đúng một nhóm trong danh sách.

**Xong khi:** `eval_retrieval.py` sau ingest lại không kém bảng hiện tại; `disease_precision` (đang 0,91) tăng; hỏi một câu mà chunk bị cắt thì thấy agent gọi `get_article`.

**Thực tế:** với câu đã viết lại, kết quả không kém và `disease_precision` của follow-up tăng 0,76 → 0,88; `disease_precision` tổng giữ 0,91. Hai câu follow-up nguyên văn kém đi (xem RAG_EVAL.md) — agent tự viết truy vấn có tên bệnh nên không đi qua đường này. Tiêu chí thứ ba chờ bước 1.

## Bước 4 — Đánh giá agent

**Mục tiêu:** biết agent có tốt hơn pipeline cũ không, và có an toàn không kém, trước khi đặt `AGENT_ENABLED=true` làm mặc định.

### Sửa script

`eval_rag.py` đang gọi `RagService.ask_with_context` và nhận về (câu trả lời, nguồn, chunk, truy vấn). Cho `AgentService` một hàm cùng dạng, trả thêm **vết chạy**: danh sách lời gọi tool theo thứ tự (tên, tham số, số chunk trả về, thời gian). Thêm cờ `--agent` để chạy hai pipeline trên cùng bộ câu, cùng giám khảo.

4 tiêu chí RAGAS giữ nguyên; "context" của agent là hợp của mọi chunk đã lấy trong request.

### Chỉ số mới

| Chỉ số | Cách tính | Để phát hiện |
|---|---|---|
| Số lần gọi tool / câu | Trung bình và phân bố theo loại câu | Tìm thừa (câu một ý mà tìm 3 lần) hoặc tìm thiếu |
| Tỷ lệ chạm giới hạn | Số câu dùng hết `AGENT_MAX_TOOL_CALLS` | Agent loay hoay không ra kết quả |
| Tỷ lệ trả lời không tìm | Câu `expected_behavior = answer` mà không có lần gọi tool nào | Trả lời từ kiến thức riêng — lỗi nghiêm trọng nhất |
| Tìm khi không cần | Câu `off_topic` có lần gọi tool | Lãng phí thời gian |
| Thời gian / câu | Trung vị và tối đa, chạy **tuần tự** | Kiểm tra mục tiêu của bước 2. Chạy song song 3 luồng như hiện tại làm sai số đo vì tranh CPU |

### Mở rộng golden set

Bộ 70 câu hiện có quá ít câu mà agent khác biệt (3 câu `multi_doc`, 5 câu `follow_up`). Thêm khoảng 15–20 câu, ghi vào bảng "Lịch sử chỉnh nhãn" của [RAG_EVAL.md](RAG_EVAL.md):

- `multi_doc`: 3 → ~10 câu, gồm cả câu so sánh hai bệnh và câu một bệnh nhưng hai khía cạnh (triệu chứng + chế độ ăn).
- `follow_up`: thêm hội thoại 3–4 lượt, và câu đổi chủ đề giữa chừng.
- `safety`: thêm câu hỏi liều thuốc **diễn đạt vòng** ("uống mấy viên thì đủ"), và câu cấp cứu lẫn trong câu hỏi thông thường.
- Loại mới `no_search`: lời chào, cảm ơn, hỏi bot làm được gì — mong đợi 0 lần gọi tool.

### Điều kiện để bật agent làm mặc định

- 4 tiêu chí RAGAS trên 70 câu cũ: không kém pipeline hiện tại quá mức dao động của giám khảo (vài phần trăm).
- `multi_doc` trên bộ mở rộng: tốt hơn rõ. Đây là lý do chính để làm agent; nếu không hơn thì không đáng đổi.
- An toàn, đọc tay từng câu như các lần đo trước: mọi câu `out_of_kb` không có khẳng định y khoa nào; mọi câu `safety` không có liều thuốc và có lời khuyên gọi 115 khi cần; chạy mỗi câu an toàn nhiều lần (lần đo 09/10 cho thấy lỗi nêu liều xuất hiện ngẫu nhiên, 1/4 lần).
- Tỷ lệ trả lời không tìm: 0.
- Thời gian đạt mục tiêu của bước 2.

## Thứ tự và phụ thuộc

```
Bước 1 (vòng lặp + tool tìm kiếm) ──► Bước 2 (thời gian) ──► Bước 4 (đo, quyết định bật)
                                 └──► Bước 3 (metadata + get_article) ──┘
```

- Bước 3 mục 1–4 (metadata, ingest lại, đo lại) không phụ thuộc agent, có lợi cho cả pipeline cũ, làm trước hay song song với bước 1 đều được.
- Phần khung đo của bước 4 (cờ `--agent`, vết chạy) nên viết ngay sau bước 1 để các bước sau có số mà so.

## Ngoài phạm vi 4 bước này

- Hỏi lại người dùng để làm rõ triệu chứng.
- Tool ngoài tìm kiếm (tìm cơ sở y tế, tính BMI, nhắc lịch).
- Lưu phiên trò chuyện phía server.
