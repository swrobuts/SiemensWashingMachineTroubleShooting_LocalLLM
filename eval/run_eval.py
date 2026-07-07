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


def run(retrieve_k: int, final_k: int, use_rerank: bool) -> int:
    from llama_index.core import Settings

    embed_model = rag_engine.DEFAULT_EMBED_MODEL
    reranker = rag_engine.get_reranker(top_n=final_k, enable=use_rerank)
    stage = (
        f"top_k={retrieve_k} → Rerank({rag_engine.RERANK_MODEL}) → {final_k}"
        if reranker else f"top_k={retrieve_k} (kein Rerank)"
    )
    print(f"🔎 Eval — Embedding: {embed_model} | {stage}\n")

    index = rag_engine.build_or_load_index(
        md_path=ROOT / "siemens_wissen.md",
        persist_dir=ROOT / "storage",
        embed_model_name=embed_model,
    )
    # Settings.embed_model wurde von build_or_load_index gesetzt.
    assert Settings.embed_model is not None
    retriever = index.as_retriever(similarity_top_k=retrieve_k)

    questions = load_questions()
    hits = 0
    recalls: list[float] = []
    misses: list[str] = []

    for q in questions:
        nodes = retriever.retrieve(q["frage"])
        if reranker:
            nodes = reranker.postprocess_nodes(nodes, query_str=q["frage"])
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
    ap.add_argument("--retrieve-k", type=int, default=rag_engine.RETRIEVE_K,
                    help="Vektor-Overfetch vor dem Reranking")
    ap.add_argument("--final-k", type=int, default=rag_engine.FINAL_K,
                    help="Anzahl Abschnitte nach dem Reranking (was das LLM sieht)")
    ap.add_argument("--no-rerank", action="store_true",
                    help="Reranking deaktivieren (nur Vektor) — für A/B-Vergleich")
    args = ap.parse_args()
    return run(args.retrieve_k, args.final_k, use_rerank=not args.no_rerank)


if __name__ == "__main__":
    raise SystemExit(main())
