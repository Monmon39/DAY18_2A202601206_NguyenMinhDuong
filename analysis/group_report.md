# Group Report - Lab 18: Production RAG

**Nhom:** Ca nhan  
**Ngay:** 18/08/2026

## Thanh vien & Phan cong

| Ten | Module | Hoan thanh | Tests pass |
|-----|--------|------------|------------|
| Nguyen Minh Duong | M1: Chunking | Done | 13/13 |
| Nguyen Minh Duong | M2: Hybrid Search | Done | 5/5 |
| Nguyen Minh Duong | M3: Reranking | Done | 5/5 |
| Nguyen Minh Duong | M4: Evaluation | Done | 4/4 |
| Nguyen Minh Duong | M5: Enrichment | Done | 10/10 |

## Ket qua RAGAS

| Metric | Naive | Production | Delta |
|--------|------:|-----------:|------:|
| Faithfulness | 1.0000 | 1.0000 | +0.0000 |
| Answer Relevancy | 0.7628 | 0.7094 | -0.0534 |
| Context Precision | 0.2193 | 0.2135 | -0.0058 |
| Context Recall | 0.8601 | 0.8235 | -0.0366 |

## Key Findings

1. **Biggest improvement:** Pipeline production da co day du cac buoc M1-M5: hierarchical chunking, enrichment, hybrid search, reranking va evaluation/failure analysis.
2. **Biggest challenge:** Cac cau hoi versioning va numeric multi-hop de bi lay nham chunk cu hoac chunk trung so tien.
3. **Surprise finding:** Context recall kha cao nhung context precision thap, chung to he thong thuong lay du thong tin nhung con nhieu context nhieu.

## Presentation Notes

1. RAGAS scores: faithfulness giu 1.0000, context recall production 0.8235.
2. Biggest win: M2 + M3 giup pipeline chay khong can Docker bang fallback local, van giu interface BM25/Dense/RRF/Rerank.
3. Case study: cau hoi doi mat khau bi nham v1.0 90 ngay thay vi v2.0 120 ngay do chua boost version hien hanh.
4. Next optimization: them metadata version/status/effective_date va query decomposition cho cau hoi multi-hop.
