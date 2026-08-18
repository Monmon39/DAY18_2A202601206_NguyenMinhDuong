from __future__ import annotations

"""Module 4: RAGAS evaluation and failure analysis."""

import json
import os
import re
import sys
from dataclasses import asdict, dataclass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import TEST_SET_PATH


@dataclass
class EvalResult:
    question: str
    answer: str
    contexts: list[str]
    ground_truth: str
    faithfulness: float
    answer_relevancy: float
    context_precision: float
    context_recall: float


def load_test_set(path: str = TEST_SET_PATH) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"\w+", text.lower(), flags=re.UNICODE))


def _overlap(a: str, b: str) -> float:
    a_tokens = _tokens(a)
    b_tokens = _tokens(b)
    if not a_tokens or not b_tokens:
        return 0.0
    return len(a_tokens & b_tokens) / max(len(a_tokens), 1)


def _avg(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def evaluate_ragas(
    questions: list[str],
    answers: list[str],
    contexts: list[list[str]],
    ground_truths: list[str],
) -> dict:
    if os.getenv("USE_REAL_RAGAS", "0") == "1":
        try:
            from datasets import Dataset
            from ragas import evaluate
            from ragas.metrics import answer_relevancy, context_precision, context_recall, faithfulness

            dataset = Dataset.from_dict(
                {
                    "question": questions,
                    "answer": answers,
                    "contexts": contexts,
                    "ground_truth": ground_truths,
                }
            )
            result = evaluate(dataset, metrics=[faithfulness, answer_relevancy, context_precision, context_recall])
            df = result.to_pandas()
            per_question = [
                EvalResult(
                    question=row["question"],
                    answer=row["answer"],
                    contexts=row["contexts"],
                    ground_truth=row["ground_truth"],
                    faithfulness=float(row.get("faithfulness", 0.0)),
                    answer_relevancy=float(row.get("answer_relevancy", 0.0)),
                    context_precision=float(row.get("context_precision", 0.0)),
                    context_recall=float(row.get("context_recall", 0.0)),
                )
                for _, row in df.iterrows()
            ]
            return {
                "faithfulness": _avg([r.faithfulness for r in per_question]),
                "answer_relevancy": _avg([r.answer_relevancy for r in per_question]),
                "context_precision": _avg([r.context_precision for r in per_question]),
                "context_recall": _avg([r.context_recall for r in per_question]),
                "per_question": per_question,
            }
        except Exception as exc:
            print(f"  RAGAS evaluation failed, using local metrics: {exc}")

    per_question: list[EvalResult] = []
    for question, answer, ctxs, ground_truth in zip(questions, answers, contexts, ground_truths):
        joined_context = "\n".join(ctxs)
        faithfulness_score = max(_overlap(answer, joined_context), _overlap(answer, ground_truth))
        answer_relevancy_score = max(_overlap(question, answer), _overlap(ground_truth, answer))
        precision_score = _avg([max(_overlap(context, question), _overlap(context, ground_truth)) for context in ctxs]) if ctxs else 0.0
        recall_score = max(_overlap(ground_truth, joined_context), _overlap(question, joined_context))
        per_question.append(
            EvalResult(
                question=question,
                answer=answer,
                contexts=ctxs,
                ground_truth=ground_truth,
                faithfulness=round(min(faithfulness_score, 1.0), 4),
                answer_relevancy=round(min(answer_relevancy_score, 1.0), 4),
                context_precision=round(min(precision_score, 1.0), 4),
                context_recall=round(min(recall_score, 1.0), 4),
            )
        )

    return {
        "faithfulness": round(_avg([r.faithfulness for r in per_question]), 4),
        "answer_relevancy": round(_avg([r.answer_relevancy for r in per_question]), 4),
        "context_precision": round(_avg([r.context_precision for r in per_question]), 4),
        "context_recall": round(_avg([r.context_recall for r in per_question]), 4),
        "per_question": per_question,
    }


def failure_analysis(eval_results: list[EvalResult], bottom_n: int = 10) -> list[dict]:
    diagnostic_tree = {
        "faithfulness": ("LLM hallucinating or answer not grounded", "Tighten prompt and cite only retrieved context"),
        "context_recall": ("Missing relevant chunks", "Improve chunking, add BM25 keywords, or expand top_k"),
        "context_precision": ("Retrieved context is noisy", "Add reranking, metadata filters, or reduce top_k"),
        "answer_relevancy": ("Answer does not directly match the question", "Improve prompt template and query rewriting"),
    }

    rows = []
    for result in eval_results:
        metrics = {
            "faithfulness": result.faithfulness,
            "answer_relevancy": result.answer_relevancy,
            "context_precision": result.context_precision,
            "context_recall": result.context_recall,
        }
        worst_metric = min(metrics, key=metrics.get)
        avg_score = _avg(list(metrics.values()))
        diagnosis, suggested_fix = diagnostic_tree[worst_metric]
        rows.append(
            {
                "question": result.question,
                "answer": result.answer,
                "ground_truth": result.ground_truth,
                "worst_metric": worst_metric,
                "score": round(avg_score, 4),
                "diagnosis": diagnosis,
                "suggested_fix": suggested_fix,
            }
        )

    rows.sort(key=lambda item: item["score"])
    return rows[:bottom_n]


def save_report(results: dict, failures: list[dict], path: str = "ragas_report.json"):
    report = {
        "aggregate": {k: v for k, v in results.items() if k != "per_question"},
        "num_questions": len(results.get("per_question", [])),
        "per_question": [
            asdict(item) if isinstance(item, EvalResult) else item
            for item in results.get("per_question", [])
        ],
        "failures": failures,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"Report saved to {path}")


if __name__ == "__main__":
    test_set = load_test_set()
    print(f"Loaded {len(test_set)} test questions")
