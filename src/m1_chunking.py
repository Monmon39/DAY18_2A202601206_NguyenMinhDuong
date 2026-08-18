from __future__ import annotations

"""Module 1: Advanced chunking strategies."""

import glob
import os
import re
import sys
from dataclasses import dataclass, field

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import DATA_DIR, HIERARCHICAL_CHILD_SIZE, HIERARCHICAL_PARENT_SIZE, SEMANTIC_THRESHOLD


@dataclass
class Chunk:
    text: str
    metadata: dict = field(default_factory=dict)
    parent_id: str | None = None


def _extract_pdf_text(path: str) -> str:
    try:
        from pypdf import PdfReader
    except Exception:
        return ""

    reader = PdfReader(path)
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n\n".join(pages).strip()


def load_documents(data_dir: str = DATA_DIR) -> list[dict]:
    docs = []
    for fp in sorted(glob.glob(os.path.join(data_dir, "*.md"))):
        with open(fp, encoding="utf-8") as f:
            docs.append({"text": f.read(), "metadata": {"source": os.path.basename(fp)}})

    for fp in sorted(glob.glob(os.path.join(data_dir, "*.pdf"))):
        text = _extract_pdf_text(fp)
        if text:
            docs.append({"text": text, "metadata": {"source": os.path.basename(fp)}})
        else:
            print(f"  Skip {os.path.basename(fp)}: scanned PDF has no text layer.")
    return docs


def chunk_basic(text: str, chunk_size: int = 500, metadata: dict | None = None) -> list[Chunk]:
    metadata = metadata or {}
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks = []
    current = ""
    for para in paragraphs:
        if len(current) + len(para) > chunk_size and current:
            chunks.append(Chunk(text=current.strip(), metadata={**metadata, "chunk_index": len(chunks)}))
            current = ""
        current += para + "\n\n"
    if current.strip():
        chunks.append(Chunk(text=current.strip(), metadata={**metadata, "chunk_index": len(chunks)}))
    return chunks


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n{2,}", text) if s.strip()]


def _lexical_similarity(a: str, b: str) -> float:
    a_tokens = set(re.findall(r"\w+", a.lower(), flags=re.UNICODE))
    b_tokens = set(re.findall(r"\w+", b.lower(), flags=re.UNICODE))
    if not a_tokens or not b_tokens:
        return 0.0
    return len(a_tokens & b_tokens) / max(len(a_tokens | b_tokens), 1)


def chunk_semantic(
    text: str,
    threshold: float = SEMANTIC_THRESHOLD,
    metadata: dict | None = None,
) -> list[Chunk]:
    metadata = metadata or {}
    sentences = _sentences(text)
    if not sentences:
        return []

    groups: list[list[str]] = [[sentences[0]]]
    try:
        if os.getenv("USE_REAL_SEMANTIC", "0") != "1":
            raise RuntimeError("Using local semantic fallback")
        from numpy import dot
        from numpy.linalg import norm
        from sentence_transformers import SentenceTransformer

        model = SentenceTransformer("all-MiniLM-L6-v2")
        embeddings = model.encode(sentences, show_progress_bar=False)

        def sim(i: int) -> float:
            return float(dot(embeddings[i - 1], embeddings[i]) / (norm(embeddings[i - 1]) * norm(embeddings[i]) + 1e-9))

    except Exception:

        def sim(i: int) -> float:
            return _lexical_similarity(sentences[i - 1], sentences[i])

    for i in range(1, len(sentences)):
        if sim(i) < threshold and len(" ".join(groups[-1])) > 120:
            groups.append([sentences[i]])
        else:
            groups[-1].append(sentences[i])

    return [
        Chunk(" ".join(group).strip(), {**metadata, "strategy": "semantic", "chunk_index": i})
        for i, group in enumerate(groups)
        if " ".join(group).strip()
    ]


def chunk_hierarchical(
    text: str,
    parent_size: int = HIERARCHICAL_PARENT_SIZE,
    child_size: int = HIERARCHICAL_CHILD_SIZE,
    metadata: dict | None = None,
) -> tuple[list[Chunk], list[Chunk]]:
    metadata = metadata or {}
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()] or ([text.strip()] if text.strip() else [])

    parents: list[Chunk] = []
    current = ""
    for para in paragraphs:
        if current and len(current) + len(para) + 2 > parent_size:
            pid = f"parent_{len(parents)}"
            parents.append(Chunk(current.strip(), {**metadata, "chunk_type": "parent", "parent_id": pid, "chunk_index": len(parents)}))
            current = ""
        current = f"{current}\n\n{para}" if current else para
    if current.strip():
        pid = f"parent_{len(parents)}"
        parents.append(Chunk(current.strip(), {**metadata, "chunk_type": "parent", "parent_id": pid, "chunk_index": len(parents)}))

    children: list[Chunk] = []
    for parent in parents:
        pid = parent.metadata["parent_id"]
        parts = _sentences(parent.text) or [parent.text]
        current_child = ""
        child_index = 0
        for part in parts:
            if current_child and len(current_child) + len(part) + 1 > child_size:
                children.append(Chunk(current_child.strip(), {**metadata, "chunk_type": "child", "child_index": child_index}, parent_id=pid))
                child_index += 1
                current_child = ""
            current_child = f"{current_child} {part}" if current_child else part
        if current_child.strip():
            children.append(Chunk(current_child.strip(), {**metadata, "chunk_type": "child", "child_index": child_index}, parent_id=pid))

    return parents, children


def chunk_structure_aware(text: str, metadata: dict | None = None) -> list[Chunk]:
    metadata = metadata or {}
    chunks: list[Chunk] = []
    current_header = ""
    current_lines: list[str] = []

    def flush() -> None:
        body = "\n".join(current_lines).strip()
        if current_header or body:
            chunk_text = f"{current_header}\n\n{body}".strip() if current_header else body
            chunks.append(
                Chunk(
                    chunk_text,
                    {
                        **metadata,
                        "section": current_header.lstrip("# ").strip() or "root",
                        "strategy": "structure",
                        "chunk_index": len(chunks),
                    },
                )
            )

    for line in text.splitlines():
        if re.match(r"^#{1,3}\s+.+$", line):
            flush()
            current_header = line.strip()
            current_lines = []
        else:
            current_lines.append(line)
    flush()
    return chunks


def compare_strategies(documents: list[dict]) -> dict:
    def _stats(chunk_list):
        lengths = [len(c.text) for c in chunk_list]
        if not lengths:
            return {"count": 0, "avg_len": 0, "min_len": 0, "max_len": 0}
        return {
            "count": len(lengths),
            "avg_len": round(sum(lengths) / len(lengths)),
            "min_len": min(lengths),
            "max_len": max(lengths),
        }

    all_text = "\n\n".join(d["text"] for d in documents)
    meta = {"source": "all"}
    basic = chunk_basic(all_text, metadata=meta)
    semantic = chunk_semantic(all_text, metadata=meta)
    parents, children = chunk_hierarchical(all_text, metadata=meta)
    structure = chunk_structure_aware(all_text, metadata=meta)
    results = {
        "basic": _stats(basic),
        "semantic": _stats(semantic),
        "hierarchical": {**_stats(children), "parents": len(parents)},
        "structure": _stats(structure),
    }

    print(f"{'Strategy':<15} {'Chunks':>7} {'Avg':>5} {'Min':>5} {'Max':>5}")
    for name, s in results.items():
        print(f"{name:<15} {s['count']:>7} {s['avg_len']:>5} {s['min_len']:>5} {s['max_len']:>5}")
    return results


if __name__ == "__main__":
    docs = load_documents()
    print(f"Loaded {len(docs)} documents")
    compare_strategies(docs)
