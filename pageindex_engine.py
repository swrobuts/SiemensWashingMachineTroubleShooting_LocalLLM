"""PageIndex-Retrieval — vectorless, reasoning-based (VectifyAI PageIndex).

Statt Vektor-Ähnlichkeit navigiert ein LLM den hierarchischen Tree-Index
(Titel + Zusammenfassungen) und wählt die relevanten Knoten aus; deren Text
bildet den Kontext. Der Baum wird offline von build_pageindex_tree.py erzeugt
(pageindex_tree.json). Läuft vollständig lokal über LM Studio (LiteLLM).

Entspricht dem offiziellen „Vectorless RAG"-Cookbook von PageIndex.
"""
from __future__ import annotations

import copy
import json
import os
import re

from pageindex import utils as pi_utils

os.environ.setdefault("LM_STUDIO_API_BASE", "http://127.0.0.1:1234/v1")
os.environ.setdefault("LM_STUDIO_API_KEY", "lm-studio")

TREE_PATH = os.getenv("PAGEINDEX_TREE", "pageindex_tree.json")
MODEL = os.getenv("PAGEINDEX_MODEL", "lm_studio/gemma-4-12b-it-mlx")
MAX_NODES = int(os.getenv("PAGEINDEX_MAX_NODES", "5"))
# Der Manual-Baum ist flach (187 ##-Abschnitte). Bei kleinem Kontextfenster wird
# die Baum-Navigation in Häppchen (Batches) mit gekürzten Summaries ausgeführt.
BATCH = int(os.getenv("PAGEINDEX_BATCH", "30"))
SUMMARY_CHARS = int(os.getenv("PAGEINDEX_SUMMARY_CHARS", "160"))

_tree = None
_node_map = None

# Original-Suchprompt (aus dem PageIndex-Cookbook), auf Deutsch.
SEARCH_PROMPT = """Du erhältst eine Frage und eine Liste von Abschnitten einer Siemens-Waschmaschinen-Bedienungsanleitung.
Jeder Abschnitt hat node_id, title und summary.
Finde die node_ids der Abschnitte, die die Antwort auf die Frage enthalten könnten. Wenn keiner passt, gib eine leere Liste zurück.

Frage: {query}

Abschnitte:
{tree}

Antworte AUSSCHLIESSLICH als JSON:
{{"node_list": ["node_id_1", "node_id_2"]}}
Gib direkt das JSON zurück, sonst nichts."""


def load_tree(path: str = TREE_PATH):
    """Lädt den Tree-Index und baut die node_id → Knoten-Map."""
    global _tree, _node_map
    with open(path, encoding="utf-8") as f:
        _tree = json.load(f)
    _node_map = pi_utils.create_node_mapping(_tree)
    return _tree


def _ensure_loaded():
    if _tree is None:
        load_tree()


def default_complete(prompt: str, model: str | None = None) -> str:
    """Ein LLM-Completion via LiteLLM (LM Studio). Für den Standalone-/Eval-Betrieb."""
    import litellm
    litellm.drop_params = True
    r = litellm.completion(
        model=model or MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
    )
    return r.choices[0].message.content or ""


def _parse_node_list(raw: str) -> list[str]:
    """Robuste Extraktion der node_list aus der LLM-Antwort."""
    txt = pi_utils.get_json_content(raw) if "```" in raw else raw
    try:
        data = json.loads(txt)
        ids = data.get("node_list", [])
        if isinstance(ids, list):
            return [str(x) for x in ids]
    except Exception:
        pass
    # Fallback: node_id-artige Zahlen aus dem Text ziehen
    return re.findall(r'"(\d{3,5})"', raw)


def _flat_nodes() -> list[dict]:
    """Kompakte Knotenliste {node_id, title, summary} (Summary gekürzt)."""
    out = []
    for nid, n in _node_map.items():
        summary = (n.get("summary") or n.get("title") or "").strip().replace("\n", " ")
        out.append({"node_id": str(nid), "title": (n.get("title") or "").strip()[:80],
                    "summary": summary[:SUMMARY_CHARS]})
    return out


def search(query: str, complete=None, max_nodes: int = MAX_NODES) -> list[dict]:
    """Vectorless Retrieval: LLM navigiert die Abschnitte (batch-weise) und wählt
    die relevanten aus; deren Knoten-Dicts (mit Volltext) werden zurückgegeben."""
    _ensure_loaded()
    complete = complete or default_complete
    items = _flat_nodes()
    selected: list[str] = []
    for i in range(0, len(items), BATCH):
        batch = items[i:i + BATCH]
        prompt = SEARCH_PROMPT.format(query=query, tree=json.dumps(batch, ensure_ascii=False))
        for nid in _parse_node_list(complete(prompt)):
            if nid in _node_map and nid not in selected:
                selected.append(nid)
    return [_node_map[nid] for nid in selected[:max_nodes]]


def retrieve_context(query: str, complete=None) -> tuple[str, list[dict]]:
    """Gibt (Kontext-Text, gewählte Knoten) für die Antwortgenerierung zurück."""
    nodes = search(query, complete=complete)
    context = "\n\n".join(n.get("text", "") for n in nodes if n.get("text"))
    return context, nodes


def is_grounded(nodes: list[dict]) -> bool:
    """Guardrail-Äquivalent: hat die Baum-Navigation relevante Knoten gefunden?"""
    return bool(nodes)


_PAGE_RE = re.compile(r"Seite\s+(\d{1,3})")


def format_source_reference(nodes: list[dict]) -> str:
    """Quellenangabe: Abschnittstitel + Seite(n) aus dem Knotentext."""
    if not nodes:
        return "Siemens Handbuch"
    title = (nodes[0].get("title") or "").strip()
    pages: list[str] = []
    for n in nodes[:3]:
        for m in _PAGE_RE.finditer(n.get("text", "")):
            if m.group(1) not in pages:
                pages.append(m.group(1))
    ref = "Handbuch"
    if title:
        ref += f": {title}"
    if pages:
        ref += " · Seite " + "/".join(pages[:3])
    return ref
