from __future__ import annotations

"""Module 2: Hybrid search with BM25, dense fallback, and RRF."""

import math
import os
import re
import sys
from collections import Counter
from dataclasses import dataclass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import BM25_TOP_K, COLLECTION_NAME, DENSE_TOP_K, HYBRID_TOP_K, QDRANT_HOST, QDRANT_PORT


@dataclass
class SearchResult:
    text: str
    score: float
    metadata: dict
    method: str


def segment_vietnamese(text: str) -> str:
    try:
        from underthesea import word_tokenize

        return word_tokenize(text, format="text").replace("_", " ")
    except Exception:
        return text


def _tokens(text: str) -> list[str]:
    segmented = segment_vietnamese(text).lower()
    return re.findall(r"\w+", segmented, flags=re.UNICODE)


def _cosine_tokens(query_tokens: list[str], doc_tokens: list[str]) -> float:
    if not query_tokens or not doc_tokens:
        return 0.0
    q_counter = Counter(query_tokens)
    d_counter = Counter(doc_tokens)
    dot = sum(q_counter[t] * d_counter.get(t, 0) for t in q_counter)
    q_norm = math.sqrt(sum(v * v for v in q_counter.values()))
    d_norm = math.sqrt(sum(v * v for v in d_counter.values()))
    return dot / (q_norm * d_norm + 1e-9)


class BM25Search:
    def __init__(self):
        self.corpus_tokens: list[list[str]] = []
        self.documents: list[dict] = []
        self.bm25 = None

    def index(self, chunks: list[dict]) -> None:
        self.documents = chunks
        self.corpus_tokens = [_tokens(chunk["text"]) for chunk in chunks]
        try:
            from rank_bm25 import BM25Okapi

            self.bm25 = BM25Okapi(self.corpus_tokens)
        except Exception:
            self.bm25 = None

    def search(self, query: str, top_k: int = BM25_TOP_K) -> list[SearchResult]:
        if not self.documents:
            return []
        query_tokens = _tokens(query)
        if not query_tokens:
            return []

        if self.bm25 is not None:
            raw_scores = list(self.bm25.get_scores(query_tokens))
        else:
            raw_scores = [_cosine_tokens(query_tokens, doc_tokens) for doc_tokens in self.corpus_tokens]

        top_indices = sorted(range(len(raw_scores)), key=lambda i: raw_scores[i], reverse=True)[:top_k]
        results = []
        for i in top_indices:
            score = float(raw_scores[i])
            if score <= 0:
                continue
            doc = self.documents[i]
            results.append(SearchResult(doc["text"], score, doc.get("metadata", {}), "bm25"))
        return results


class DenseSearch:
    def __init__(self):
        self.client = None
        self._encoder = None
        self._collections: dict[str, list[dict]] = {}
        self._collection_tokens: dict[str, list[list[str]]] = {}
        try:
            from qdrant_client import QdrantClient

            self.client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT, timeout=1.0)
        except Exception:
            self.client = None

    def _get_encoder(self):
        if self._encoder is None:
            from config import EMBEDDING_MODEL
            from sentence_transformers import SentenceTransformer

            self._encoder = SentenceTransformer(EMBEDDING_MODEL)
        return self._encoder

    def index(self, chunks: list[dict], collection: str = COLLECTION_NAME) -> None:
        self._collections[collection] = chunks
        self._collection_tokens[collection] = [_tokens(chunk["text"]) for chunk in chunks]

        if self.client is None or os.getenv("FAKE_QDRANT", "1") == "1":
            return

        try:
            from config import EMBEDDING_DIM
            from qdrant_client.models import Distance, PointStruct, VectorParams

            self.client.recreate_collection(
                collection_name=collection,
                vectors_config=VectorParams(size=EMBEDDING_DIM, distance=Distance.COSINE),
            )
            texts = [c["text"] for c in chunks]
            vectors = self._get_encoder().encode(texts, show_progress_bar=False)
            points = [
                PointStruct(id=i, vector=vector.tolist(), payload={**chunk.get("metadata", {}), "text": chunk["text"]})
                for i, (chunk, vector) in enumerate(zip(chunks, vectors))
            ]
            self.client.upsert(collection_name=collection, points=points)
        except Exception:
            self.client = None

    def search(self, query: str, top_k: int = DENSE_TOP_K, collection: str = COLLECTION_NAME) -> list[SearchResult]:
        if self.client is not None and os.getenv("FAKE_QDRANT", "1") != "1":
            try:
                query_vector = self._get_encoder().encode(query).tolist()
                response = self.client.query_points(collection_name=collection, query=query_vector, limit=top_k)
                return [
                    SearchResult(pt.payload.get("text", ""), float(pt.score), dict(pt.payload or {}), "dense")
                    for pt in response.points
                ]
            except Exception:
                self.client = None

        docs = self._collections.get(collection, [])
        tokenized_docs = self._collection_tokens.get(collection, [])
        query_tokens = _tokens(query)
        scored = [
            (i, _cosine_tokens(query_tokens, doc_tokens))
            for i, doc_tokens in enumerate(tokenized_docs)
        ]
        scored.sort(key=lambda x: x[1], reverse=True)
        results = []
        for i, score in scored[:top_k]:
            if score <= 0:
                continue
            doc = docs[i]
            results.append(SearchResult(doc["text"], float(score), doc.get("metadata", {}), "dense"))
        return results


def reciprocal_rank_fusion(
    results_list: list[list[SearchResult]],
    k: int = 60,
    top_k: int = HYBRID_TOP_K,
) -> list[SearchResult]:
    rrf_scores: dict[str, dict] = {}
    for result_list in results_list:
        for rank, result in enumerate(result_list):
            if result.text not in rrf_scores:
                rrf_scores[result.text] = {"score": 0.0, "result": result}
            rrf_scores[result.text]["score"] += 1.0 / (k + rank + 1)

    merged = sorted(rrf_scores.values(), key=lambda item: item["score"], reverse=True)[:top_k]
    return [
        SearchResult(
            item["result"].text,
            float(item["score"]),
            item["result"].metadata,
            "hybrid",
        )
        for item in merged
    ]


class HybridSearch:
    def __init__(self):
        self.bm25 = BM25Search()
        self.dense = DenseSearch()

    def index(self, chunks: list[dict]) -> None:
        self.bm25.index(chunks)
        self.dense.index(chunks)

    def search(self, query: str, top_k: int = HYBRID_TOP_K) -> list[SearchResult]:
        bm25_results = self.bm25.search(query, top_k=BM25_TOP_K)
        dense_results = self.dense.search(query, top_k=DENSE_TOP_K)
        return reciprocal_rank_fusion([bm25_results, dense_results], top_k=top_k)


if __name__ == "__main__":
    print(segment_vietnamese("Nhan vien duoc nghi phep nam"))
