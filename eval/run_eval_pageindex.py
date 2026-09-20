"""Retrieval-Eval für den PageIndex-Modus (vectorless, reasoning-based).

Gleiche 10 Fragen und Metriken wie eval/run_eval.py, aber das Retrieval erfolgt
über die LLM-Abschnittsauswahl (pageindex_engine). Braucht LM Studio mit einem
geladenen Chatmodell. Gemessen wird ein Stichwort-Proxy, keine Antwortqualität.

Aufruf (aus dem Projekt-Wurzelverzeichnis)::

    python eval/run_eval_pageindex.py
    python eval/run_eval_pageindex.py --output docs/evaluation/pageindex.json
    PAGEINDEX_SUMMARY_CHARS=80 python eval/run_eval_pageindex.py --label "Summary 80"
"""
from __future__ import annotations
import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pageindex_engine as pe  # noqa: E402


def load_questions():
    return json.loads((ROOT / "eval" / "questions.json").read_text(encoding="utf-8"))["questions"]


def run(output: Path | None = None, label: str = "", min_hit_rate: float = 0.0) -> int:
    from llm_client import make_llm

    pe.load_tree(str(ROOT / "pageindex_tree.json"))
    llm = make_llm()
    model = llm.model_id()
    print(f"🌳 PageIndex-Eval | Modell {model} | Batch {pe.BATCH} | Summary {pe.SUMMARY_CHARS} Zeichen"
          + (f" | {label}" if label else "") + "\n")
    questions = load_questions()
    hits = h1 = 0
    recalls, rrs, misses, records = [], [], [], []
    t_all = time.perf_counter()
    for q in questions:
        calls = []

        def complete(prompt, _calls=calls):
            started = time.perf_counter()
            out = llm.complete(prompt)
            _calls.append({"seconds": round(time.perf_counter() - started, 2), "prompt_chars": len(prompt)})
            return out

        t0 = time.perf_counter()
        nodes = pe.search(q["frage"], complete=complete)
        seconds = time.perf_counter() - t0
        expect = [k.lower() for k in q["expect"]]
        per_node = [[k for k in expect if k in (n.get("text", "").lower())] for n in nodes]
        found = sorted({k for ks in per_node for k in ks})
        recall = len(found) / len(expect) if expect else 0.0
        recalls.append(recall)
        rank = next((i for i, ks in enumerate(per_node) if ks), None)
        rr = 1 / (rank + 1) if rank is not None else 0.0
        rrs.append(rr)
        h1 += int(rank == 0)
        hits += int(bool(found))
        records.append({"id": q["id"], "question": q["frage"], "matched_keywords": found,
                        "keyword_coverage": recall, "reciprocal_rank": rr,
                        "selected": [{"node_id": n.get("node_id"), "title": n.get("title", "")} for n in nodes],
                        "llm_calls": len(calls), "prompt_chars": sum(c["prompt_chars"] for c in calls),
                        "seconds": round(seconds, 1)})
        mark = "✅" if found else "❌"
        pos = f"Rang {rank + 1}" if rank is not None else "—"
        print(f"{mark} [{q['id']}] Recall {recall:.0%} | 1. Treffer {pos} | {len(calls)} Aufrufe, {seconds:.0f}s | {found}")
        if not found:
            misses.append(q["id"])
    n = len(questions)
    total = time.perf_counter() - t_all
    print("\n" + "=" * 50)
    print(f"Trefferquote: {hits}/{n} = {hits/n:.0%}")
    print(f"hit@1:        {h1}/{n} = {h1/n:.0%}")
    print(f"MRR:          {sum(rrs)/n:.2f}")
    print(f"Ø Recall:     {sum(recalls)/n:.0%}")
    print(f"Ø Latenz/Frage: {total/n:.0f}s")
    if misses:
        print(f"Verfehlt: {', '.join(misses)}")
    print("=" * 50)
    report = {"metric_note": "Keyword-based retrieval proxy, not answer correctness or judged document recall.",
              "mode": "pageindex", "label": label, "model": model,
              "batch": pe.BATCH, "summary_chars": pe.SUMMARY_CHARS, "max_nodes": pe.MAX_NODES,
              "evaluation_stage": "selected_sections_before_answer_context_budget",
              "questions": n, "keyword_hit_rate": hits / n, "keyword_hit_at_1": h1 / n,
              "keyword_mrr": sum(rrs) / n, "keyword_coverage": sum(recalls) / n,
              "llm_calls": sum(r["llm_calls"] for r in records),
              "query_seconds": total, "results": records}
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Protokoll: {output}")
    return 0 if hits / n >= min_hit_rate else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="PageIndex-Retrieval-Eval (mit LM Studio)")
    ap.add_argument("--output", type=Path, help="JSON-Messprotokoll")
    ap.add_argument("--label", default="", help="Kurzbezeichnung der Variante im Protokoll")
    ap.add_argument("--min-hit-rate", type=float, default=0.0)
    args = ap.parse_args()
    return run(args.output, args.label, args.min_hit_rate)


if __name__ == "__main__":
    raise SystemExit(main())
