"""Retrieval-Eval für den PageIndex-Modus (vectorless, reasoning-based).

Gleiche 10 Fragen und Metriken wie eval/run_eval.py, aber das Retrieval erfolgt
über die LLM-Baum-Navigation (pageindex_engine). Braucht LM Studio.

Aufruf (aus dem Projekt-Wurzelverzeichnis):  python3 eval/run_eval_pageindex.py
"""
from __future__ import annotations
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pageindex_engine as pe


def load_questions():
    return json.loads((ROOT / "eval" / "questions.json").read_text(encoding="utf-8"))["questions"]


def run():
    pe.load_tree(str(ROOT / "pageindex_tree.json"))
    print(f"🌳 PageIndex-Eval | Modell {pe.MODEL} | Batch {pe.BATCH}\n")
    questions = load_questions()
    hits = h1 = 0
    recalls, rrs, misses = [], [], []
    t0 = time.time()
    for q in questions:
        nodes = pe.search(q["frage"])
        expect = [k.lower() for k in q["expect"]]
        per_node = [[k for k in expect if k in (n.get("text", "").lower())] for n in nodes]
        found = sorted({k for ks in per_node for k in ks})
        recalls.append(len(found) / len(expect) if expect else 0.0)
        rank = next((i for i, ks in enumerate(per_node) if ks), None)
        rrs.append(1 / (rank + 1) if rank is not None else 0.0)
        h1 += int(rank == 0)
        hits += int(bool(found))
        mark = "✅" if found else "❌"
        pos = f"Rang {rank + 1}" if rank is not None else "—"
        print(f"{mark} [{q['id']}] Recall {len(found)/len(expect):.0%} | 1. Treffer {pos} | {found}")
        if not found:
            misses.append(q["id"])
    n = len(questions)
    print("\n" + "=" * 50)
    print(f"Trefferquote: {hits}/{n} = {hits/n:.0%}")
    print(f"hit@1:        {h1}/{n} = {h1/n:.0%}")
    print(f"MRR:          {sum(rrs)/n:.2f}")
    print(f"Ø Recall:     {sum(recalls)/n:.0%}")
    print(f"Ø Latenz/Frage: {(time.time()-t0)/n:.0f}s")
    if misses:
        print(f"Verfehlt: {', '.join(misses)}")
    print("=" * 50)


if __name__ == "__main__":
    run()
