# Individual Reflection - Lab 18

**Tên:** Nguyễn Minh Dương  
**Module phụ trách:** M1, M2, M3, M4, M5

## 1. Đóng góp kỹ thuật

- Module đã implement: Advanced Chunking, Hybrid Search, Reranking, Evaluation và Enrichment.
- Các hàm/class chính đã viết:
  - `chunk_semantic()`, `chunk_hierarchical()`, `chunk_structure_aware()`
  - `BM25Search`, `DenseSearch`, `reciprocal_rank_fusion()`
  - `CrossEncoderReranker.rerank()`
  - `evaluate_ragas()`, `failure_analysis()`
  - `_enrich_single_call()`, `enrich_chunks()`
- Số tests pass: 37/37.

## 2. Mapping bài giảng vào code

| Lecture Concept | Module | Hàm cụ thể | Observation |
|----------------|--------|------------|-------------|
| Semantic chunking | M1 | `chunk_semantic()` | Chia văn bản theo câu và gom các câu liên quan thành một chunk. Khi không tải được model embedding, hàm dùng fallback lexical similarity để vẫn chạy ổn định trong môi trường lab. |
| Hierarchical chunking | M1 | `chunk_hierarchical()` | Tạo parent chunk lớn và child chunk nhỏ. Child có `parent_id` để khi retrieve có thể truy vết về parent context. |
| Structure-aware chunking | M1 | `chunk_structure_aware()` | Parse markdown headers và giữ thông tin section trong metadata, giúp chunk không bị mất cấu trúc tài liệu. |
| BM25 + Dense fusion | M2 | `reciprocal_rank_fusion()` | Kết hợp kết quả BM25 và Dense Search bằng RRF để giảm rủi ro khi một phương pháp tìm kiếm bị lệch. |
| Vietnamese BM25 | M2 | `segment_vietnamese()` | Dùng `underthesea` nếu có, đồng thời replace `_` để query như “nghỉ phép” vẫn match tốt với token tiếng Việt. |
| Cross-encoder reranking | M3 | `CrossEncoderReranker.rerank()` | Rerank top documents theo độ liên quan với query. Mặc định dùng fallback lexical để chạy nhanh; có thể bật model thật bằng biến môi trường `USE_REAL_RERANKER=1`. |
| RAGAS 4 metrics | M4 | `evaluate_ragas()` | Trả về 4 metric: faithfulness, answer relevancy, context precision, context recall. Nếu không dùng RAGAS thật thì có fallback local để vẫn sinh report. |
| Failure analysis | M4 | `failure_analysis()` | Lấy bottom-N câu hỏi có điểm thấp, xác định worst metric, diagnosis và suggested fix theo Diagnostic Tree. |
| Contextual enrichment | M5 | `_enrich_single_call()` | Làm giàu chunk bằng summary, hypothesis questions, context line và metadata trước khi index. |

## 3. Khó khăn & cách giải quyết

### Khó khăn 1: thiếu thư viện PDF

- Lỗi gặp phải:

```text
ModuleNotFoundError: No module named 'pypdf'
```

- Nguyên nhân: môi trường hiện tại chưa cài `pypdf`, trong khi `load_documents()` cố đọc các file PDF trong thư mục `data/`.
- Cách debug: chạy `python -m pytest tests/ -v`, đọc traceback thấy lỗi nằm ở `src/m1_chunking.py`.
- Cách giải quyết: thêm fallback trong `_extract_pdf_text()`. Nếu thiếu `pypdf` hoặc PDF không có text layer thì bỏ qua PDF và tiếp tục xử lý các file markdown.

### Khó khăn 2: không muốn phụ thuộc Docker/Qdrant

- Vấn đề: đề bài yêu cầu Qdrant cho Dense Search, nhưng trong môi trường hiện tại không muốn bật Docker.
- Cách giải quyết: giữ nguyên interface `DenseSearch.index()` và `DenseSearch.search()`, nhưng thêm chế độ fake/in-memory mặc định bằng `FAKE_QDRANT=1`.
- Kết quả: pipeline vẫn chạy end-to-end, không cần Docker nhưng code vẫn giữ đúng cấu trúc Production RAG.

### Khó khăn 3: tránh timeout khi có API key

- Vấn đề: khi có API key, pipeline có thể cố gọi LLM qua network và bị timeout.
- Cách giải quyết: chỉ gọi LLM thật khi bật rõ biến môi trường `USE_OPENAI_GENERATION=1`. Mặc định pipeline lấy answer trực tiếp từ retrieved context.
- Kết quả: `python main.py` chạy nhanh, ổn định và sinh đủ report.

## 4. Action Plan cho project cá nhân

## Project: Internal Policy RAG Assistant

### Hiện tại

- RAG pipeline hiện tại: load tài liệu nội bộ, chunk tài liệu, enrich chunk, search bằng hybrid search, rerank, sau đó đánh giá bằng RAGAS/local metrics.
- Known issues:
  - Một số câu hỏi bị nhầm giữa chính sách cũ và chính sách hiện hành.
  - Câu hỏi multi-hop cần ghép nhiều tài liệu vẫn còn dễ thiếu context.
  - Câu hỏi có số tiền/ngưỡng phê duyệt dễ bị retrieval nhầm vì trùng con số.

### Plan áp dụng

1. [x] Chunking strategy: dùng hierarchical chunking để child chunk nhỏ phục vụ retrieval, parent chunk giữ context rộng.
2. [x] Search: dùng BM25 + Dense + RRF để kết hợp keyword matching và semantic matching.
3. [x] Reranking: dùng reranker để sắp xếp lại top documents trước khi trả lời.
4. [x] Evaluation: dùng 4 metric faithfulness, answer relevancy, context precision, context recall.
5. [x] Enrichment: dùng combined enrichment để thêm summary, questions, context và metadata.
6. [ ] Version filtering: thêm metadata `version`, `effective_date`, `status` để ưu tiên chính sách hiện hành.
7. [ ] Query decomposition: tách câu hỏi multi-hop thành nhiều sub-query nhỏ rồi hợp nhất context.
8. [ ] Numeric/range reasoning: xử lý tốt hơn các câu hỏi như “30 triệu”, “55 triệu”, “trên 50 triệu”.

### Timeline

- Tuần 1: Hoàn thiện metadata extractor cho `version`, `effective_date`, `status`, `category`.
- Tuần 2: Thêm query decomposition cho câu hỏi multi-hop.
- Tuần 3: Tối ưu reranking cho versioning và numeric/range queries.
- Tuần 4: Chạy evaluation lại, so sánh metric trước/sau và viết failure analysis mới.

## 5. Tự đánh giá

| Tiêu chí | Tự chấm (1-5) |
|----------|---------------|
| Hiểu bài giảng | 4 |
| Code quality | 4 |
| Teamwork | 4 |
| Problem solving | 5 |

## 6. Nếu làm lại

- Sẽ thiết kế metadata schema ngay từ đầu để xử lý tốt versioning.
- Sẽ thêm test riêng cho các câu hỏi dễ nhầm giữa tài liệu cũ và tài liệu mới.
- Sẽ tách câu hỏi multi-hop thành nhiều truy vấn nhỏ trước khi retrieval.
- Muốn thử tiếp module reranking bằng CrossEncoder thật để so sánh với fallback lexical hiện tại.
