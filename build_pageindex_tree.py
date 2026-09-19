"""Erzeugt den PageIndex-Tree-Index aus siemens_wissen.md — lokal via LM Studio.

Offline-Schritt (einmalig). Baut aus den Markdown-Überschriften einen
hierarchischen Baum, in dem jeder Knoten Titel, Text und eine LLM-generierte
Zusammenfassung trägt. Ergebnis: pageindex_tree.json.

Aufruf:  python3 build_pageindex_tree.py
Config per ENV: PAGEINDEX_MODEL (litellm-Name), LM_STUDIO_API_BASE, LM_STUDIO_API_KEY
"""
from __future__ import annotations
import asyncio
import json
import os
import time
import hashlib
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

os.environ.setdefault("LM_STUDIO_API_BASE", "http://127.0.0.1:1234/v1")
os.environ.setdefault("LM_STUDIO_API_KEY", "lm-studio")

from pageindex import md_to_tree

MODEL = os.getenv("PAGEINDEX_MODEL")
MD = ROOT / "siemens_wissen.md"
OUT = Path(os.getenv("PAGEINDEX_TREE", str(ROOT / "pageindex_tree.json")))


async def main():
    t0 = time.time()
    if not MODEL:
        raise ValueError("PAGEINDEX_MODEL auf lm_studio/<Modell-ID> setzen.")
    print(f"🌳 Baue PageIndex-Tree aus {MD} mit {MODEL} …")
    tree = await md_to_tree(
        str(MD),
        if_add_node_summary="yes",
        summary_token_threshold=200,   # Knoten > 200 Tokens werden zusammengefasst
        if_add_node_text="yes",
        if_add_node_id="yes",
        model=MODEL,
    )
    # md_to_tree gibt entweder eine Liste (structure) oder ein Dict zurück
    structure = tree.get("structure", tree) if isinstance(tree, dict) else tree
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"source_sha256": hashlib.sha256(MD.read_bytes()).hexdigest(),
                   "model": MODEL, "structure": structure}, f, ensure_ascii=False, indent=1)

    def count(nodes):
        return sum(1 + count(n.get("nodes", [])) for n in nodes)

    print(f"✅ Tree gebaut in {time.time()-t0:.0f}s — {count(structure)} Knoten → {OUT}")


if __name__ == "__main__":
    asyncio.run(main())
