"""Retrieval-Eval für den Siemens-Troubleshooting-RAG.

Misst, wie oft der Vektor-Retriever für reale Störungsfragen den *richtigen*
Handbuch-Abschnitt findet — komplett OHNE Antwort-LLM (nur das lokale Embedding
wird gebraucht). Ideal, um vor/nach jeder Retrieval-Änderung objektiv zu sehen,
ob es besser wird.

Aufruf (aus dem Projekt-Wurzelverzeichnis, LM Studio NICHT nötig)::

    python eval/run_eval.py
    EMBED_MODEL=intfloat/multilingual-e5-base python eval/run_eval.py
    python eval/run_eval.py --top-k 8

Beim ersten Lauf wird das Embedding-Modell heruntergeladen und der Index gebaut.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import rag_engine  # noqa: E402  (nach sys.path-Anpassung)


def load_questions() -> list[dict]:
    data = json.loads((ROOT / "eval" / "questions.json").read_text(encoding="utf-8"))
    return data["questions"]


def retrieved_text(nodes) -> str:
    return "\n".join(n.get_content() for n in nodes).lower()


def run(top_k: int) -> int:
    from llama_index.core import Settings

    embed_model = rag_engine.DEFAULT_EMBED_MODEL
    print(f"🔎 Eval — Embedding: {embed_model} | top_k={top_k}\n")

    index = rag_engine.build_or_load_index(
        md_path=ROOT / "siemens_wissen.md",
        persist_dir=ROOT / "storage",
        embed_model_name=embed_model,
    )
    # Settings.embed_model wurde von build_or_load_index gesetzt.
    assert Settings.embed_model is not None
    retriever = index.as_retriever(similarity_top_k=top_k)

    questions = load_questions()
    hits = 0
    recalls: list[float] = []
    misses: list[str] = []

    for q in questions:
        nodes = retriever.retrieve(q["frage"])
        ctx = retrieved_text(nodes)
        expect = [kw.lower() for kw in q["expect"]]
        found = [kw for kw in expect if kw in ctx]
        recall = len(found) / len(expect) if expect else 0.0
        recalls.append(recall)
        is_hit = len(found) > 0
        hits += int(is_hit)
        mark = "✅" if is_hit else "❌"
        print(f"{mark} [{q['id']}] Recall {recall:.0%}  gefunden={found}")
        if not is_hit:
            misses.append(q["id"])

    n = len(questions)
    print("\n" + "=" * 50)
    print(f"Trefferquote (≥1 Stichwort): {hits}/{n} = {hits / n:.0%}")
    print(f"Ø Recall über alle Stichwörter: {sum(recalls) / n:.0%}")
    if misses:
        print(f"Verfehlt: {', '.join(misses)}")
    print("=" * 50)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Retrieval-Eval (ohne LLM)")
    ap.add_argument("--top-k", type=int, default=rag_engine.DEFAULT_TOP_K)
    args = ap.parse_args()
    return run(args.top_k)


if __name__ == "__main__":
    raise SystemExit(main())
