"""Erzeugt deutsche, stichwortdichte Kurzfassungen für die PageIndex-Knoten — lokal via LM Studio.

Offline-Schritt, wiederholbar. Ersetzt in pageindex_tree.json das Feld ``summary``
jedes Knotens; Titel, Text, IDs und Quellhash bleiben unverändert. Die Kurzfassung
ist das, was das Modell bei der Abschnittsauswahl liest — sie soll deshalb Bauteile,
Bedienelemente und Störungsbilder nennen, nicht den Abschnitt beschreiben.

Regeln:
* Abschnitte bis SUMMARY_MAX Zeichen werden wörtlich übernommen (kein Modellaufruf).
* Jeder Fehlercode des Abschnitts (E:18, E:23 …) steht am Anfang der Kurzfassung,
  damit er auch nach der Kürzung auf PAGEINDEX_SUMMARY_CHARS sichtbar bleibt.
* Länge höchstens SUMMARY_MAX Zeichen, eine Zeile, keine Anführungszeichen.

Aufruf:  python build_pageindex_summaries.py [--dry-run] [--limit N]
Config: LOCAL_LLM_MODEL (profiles/local/.env), PAGEINDEX_TREE
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

SUMMARY_MAX = int(os.getenv("PAGEINDEX_SUMMARY_MAX", "160"))
PROMPT_VERSION = "de-stichwort-v1"
TREE = Path(os.getenv("PAGEINDEX_TREE", str(ROOT / "pageindex_tree.json")))

PROMPT = """Fasse den folgenden Abschnitt einer Siemens-Waschmaschinen-Bedienungsanleitung als eine Zeile Suchstichwörter zusammen, durch Kommas getrennt: die behandelten Bauteile, Bedienelemente, Programme, Störungsbilder und Handgriffe, so wie sie im Text heißen. Höchstens {max_chars} Zeichen, Deutsch, keine Kategorienamen wie "Thema:" oder "Bauteile:", keine Einleitung, keine Anführungszeichen. Nenne jeden Fehlercode (z. B. E:18) wörtlich.

Titel: {title}

Abschnitt:
{text}

Stichwortzeile:"""

_CODE = re.compile(r"\bE:\d{2,3}\b")


def plain_text(text: str) -> str:
    """Abschnittstext ohne Titelzeile, Whitespace normalisiert."""
    text = re.sub(r"^##[^\n]*(\n|$)", "", text.strip())
    return " ".join(text.split())


def codes_in(text: str) -> list[str]:
    return sorted(set(_CODE.findall(text)), key=lambda c: (len(c), c))


def normalize_summary(raw: str, text: str, max_chars: int = SUMMARY_MAX) -> str:
    """Erste brauchbare Zeile der Modellantwort, Codes vorangestellt, auf max_chars gekürzt."""
    line = ""
    for candidate in raw.strip().splitlines():
        candidate = re.sub(r"^\W*(Stichwortzeile|Kurzfassung|Zusammenfassung)\s*:\s*", "", candidate.strip(), flags=re.I)
        candidate = candidate.strip().strip("`\"'„“”*- ").strip()
        if candidate:
            line = candidate
            break
    line = " ".join(line.split())
    # Kategorienamen aus dem Prompt und leere Felder entfernen ("Bedienelemente: -").
    line = re.sub(r"\b(Thema|Bauteile|Bedienelemente|Programme|Störungsbilder|Handgriffe|Fehlercodes?)\s*:\s*(-\s*[;,]?\s*)?", "", line)
    line = re.sub(r"\s*[;,]\s*(?=[;,])", "", line).strip(" ,;")
    codes = codes_in(text)
    # Codes an den Anfang, damit sie die Kürzung auf PAGEINDEX_SUMMARY_CHARS überleben.
    prefix = (", ".join(codes) + " · ") if codes else ""
    line = prefix + line
    if len(line) > max_chars:
        cut = line[:max_chars]
        space = cut.rfind(" ")
        if space > len(prefix):
            cut = cut[:space]
        line = cut.rstrip(" ,;:·-")
    return line


def build_summary(node: dict, complete, max_chars: int = SUMMARY_MAX) -> tuple[str, bool]:
    """(Kurzfassung, Modell benutzt?)"""
    text = plain_text(node.get("text", ""))
    if len(text) <= max_chars:
        return normalize_summary(text, text, max_chars), False
    raw = complete(PROMPT.format(max_chars=max_chars, title=node.get("title", "").strip(), text=text))
    summary = normalize_summary(raw, text, max_chars)
    if not summary:
        summary = normalize_summary(text, text, max_chars)
    return summary, True


def main() -> int:
    ap = argparse.ArgumentParser(description="PageIndex-Kurzfassungen neu erzeugen (LM Studio)")
    ap.add_argument("--dry-run", action="store_true", help="nur anzeigen, Datei nicht schreiben")
    ap.add_argument("--limit", type=int, default=0, help="nur die ersten N Knoten (zum Ausprobieren)")
    args = ap.parse_args()

    from llm_client import make_llm
    llm = make_llm()
    model = llm.model_id()
    data = json.loads(TREE.read_text(encoding="utf-8"))
    nodes = data["structure"]
    if any(n.get("nodes") for n in nodes):
        raise SystemExit("Hierarchischer Baum: dieses Skript erwartet die flache Abschnittsliste.")
    todo = nodes[: args.limit] if args.limit else nodes
    print(f"✍️  {len(todo)} Knoten, Modell {model}, max {SUMMARY_MAX} Zeichen …")
    t0 = time.time()
    used_model = 0
    for i, node in enumerate(todo, 1):
        summary, via_model = build_summary(node, llm.complete)
        used_model += int(via_model)
        node["summary"] = summary
        print(f"{i:3d}/{len(todo)} {'LLM' if via_model else 'txt'} {node['node_id']} {summary[:90]}")
    data["summary_model"] = model
    data["summary_prompt"] = PROMPT_VERSION
    data["summary_generated"] = dt.date.today().isoformat()
    data["provenance"] = (
        "Legacy tree; every stored node text verified against Markdown on 2026-09-19. "
        f"Summaries regenerated in German ({PROMPT_VERSION}) with {model} on {data['summary_generated']}; "
        "sections up to {0} characters copied verbatim.".format(SUMMARY_MAX))
    if args.dry_run:
        print("Dry-Run: Datei nicht geschrieben.")
        return 0
    TREE.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"✅ {len(todo)} Kurzfassungen ({used_model} per Modell) in {time.time()-t0:.0f}s → {TREE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
