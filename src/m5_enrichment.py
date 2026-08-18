from __future__ import annotations

"""Module 5: Chunk enrichment pipeline."""

import json
import os
import re
import sys
from dataclasses import dataclass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import OPENAI_API_KEY


@dataclass
class EnrichedChunk:
    original_text: str
    enriched_text: str
    summary: str
    hypothesis_questions: list[str]
    auto_metadata: dict
    method: str


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", text) if s.strip()]


def _keywords(text: str, limit: int = 6) -> list[str]:
    stopwords = {
        "la", "va", "cua", "cho", "trong", "duoc", "cac", "mot", "nhan", "vien",
        "the", "can", "phai", "ngay", "nam", "voi", "khi", "neu", "hoac",
    }
    tokens = re.findall(r"\w+", text.lower(), flags=re.UNICODE)
    counts: dict[str, int] = {}
    for token in tokens:
        if len(token) <= 2 or token in stopwords:
            continue
        counts[token] = counts.get(token, 0) + 1
    return [token for token, _ in sorted(counts.items(), key=lambda item: item[1], reverse=True)[:limit]]


def summarize_chunk(text: str) -> str:
    if OPENAI_API_KEY and os.getenv("USE_OPENAI_ENRICHMENT", "0") == "1":
        try:
            from openai import OpenAI

            client = OpenAI()
            resp = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "Tom tat doan van sau trong 2 cau ngan gon bang tieng Viet."},
                    {"role": "user", "content": text},
                ],
                max_tokens=150,
            )
            return resp.choices[0].message.content.strip()
        except Exception:
            pass

    sentences = _sentences(text)
    return ". ".join(sentences[:2]).strip() + ("." if sentences else "")


def generate_hypothesis_questions(text: str, n_questions: int = 3) -> list[str]:
    if OPENAI_API_KEY and os.getenv("USE_OPENAI_ENRICHMENT", "0") == "1":
        try:
            from openai import OpenAI

            client = OpenAI()
            resp = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": f"Tao {n_questions} cau hoi ma doan van co the tra loi, moi cau mot dong."},
                    {"role": "user", "content": text},
                ],
                max_tokens=200,
            )
            questions = resp.choices[0].message.content.strip().splitlines()
            return [q.strip().lstrip("0123456789.-) ") for q in questions if q.strip()][:n_questions]
        except Exception:
            pass

    sentences = _sentences(text)
    questions = []
    for sentence in sentences[:n_questions]:
        topic = " ".join(_keywords(sentence, 4)) or sentence[:40]
        questions.append(f"{topic} la gi?")
    return questions[:n_questions]


def contextual_prepend(text: str, document_title: str = "") -> str:
    source = document_title or "tai lieu noi bo"
    keywords = ", ".join(_keywords(text, 4)) or "chinh sach"
    context = f"Trich tu {source}; noi dung lien quan den {keywords}."
    return f"{context}\n\n{text}"


def extract_metadata(text: str) -> dict:
    lowered = text.lower()
    if any(term in lowered for term in ["mat khau", "vpn", "bao mat", "mfa"]):
        category = "it"
    elif any(term in lowered for term in ["luong", "thuong", "chi phi", "tam ung"]):
        category = "finance"
    elif any(term in lowered for term in ["nghi", "thu viec", "dao tao", "mentor"]):
        category = "hr"
    else:
        category = "policy"

    years = re.findall(r"\b20\d{2}\b", text)
    return {
        "topic": ", ".join(_keywords(text, 3)) or "general",
        "entities": _keywords(text, 5),
        "category": category,
        "language": "vi",
        "date_range": sorted(set(years)),
    }


def _enrich_single_call(text: str, source: str) -> dict:
    if OPENAI_API_KEY and os.getenv("USE_OPENAI_ENRICHMENT", "0") == "1":
        try:
            from openai import OpenAI

            client = OpenAI()
            resp = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Tra ve JSON gom summary, questions, context, metadata. "
                            "metadata co topic, entities, category, language."
                        ),
                    },
                    {"role": "user", "content": f"Tai lieu: {source}\n\nDoan van:\n{text}"},
                ],
                max_tokens=400,
            )
            return json.loads(resp.choices[0].message.content)
        except Exception:
            pass

    return {
        "summary": summarize_chunk(text),
        "questions": generate_hypothesis_questions(text),
        "context": f"Trich tu {source or 'tai lieu noi bo'}; noi dung chunk duoc lam giau de truy hoi tot hon.",
        "metadata": extract_metadata(text),
    }


def enrich_chunks(chunks: list[dict], methods: list[str] | None = None) -> list[EnrichedChunk]:
    if methods is None:
        methods = ["combined"]

    use_combined = "combined" in methods
    enriched = []
    for i, chunk in enumerate(chunks):
        text = chunk["text"]
        source = chunk.get("metadata", {}).get("source", "")

        if use_combined:
            result = _enrich_single_call(text, source)
            summary = result.get("summary", "")
            questions = result.get("questions", [])
            context_line = result.get("context", "")
            enriched_text = f"{context_line}\n\n{text}" if context_line else text
            auto_meta = result.get("metadata", {})
        else:
            summary = summarize_chunk(text) if "summary" in methods else ""
            questions = generate_hypothesis_questions(text) if "hyqa" in methods else []
            enriched_text = contextual_prepend(text, source) if "contextual" in methods else text
            auto_meta = extract_metadata(text) if "metadata" in methods else {}

        enriched.append(
            EnrichedChunk(
                original_text=text,
                enriched_text=enriched_text,
                summary=summary,
                hypothesis_questions=questions,
                auto_metadata={**chunk.get("metadata", {}), **auto_meta},
                method="+".join(methods),
            )
        )

        if (i + 1) % 10 == 0 or (i + 1) == len(chunks):
            print(f"  Enriched {i + 1}/{len(chunks)} chunks...", flush=True)
    return enriched


if __name__ == "__main__":
    sample = "Nhan vien chinh thuc duoc nghi phep nam 12 ngay lam viec moi nam."
    print(summarize_chunk(sample))
    print(generate_hypothesis_questions(sample))
    print(contextual_prepend(sample, "policy.md"))
    print(extract_metadata(sample))
