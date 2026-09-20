"""PageIndex: vereinfachte Batch-Auswahl von Abschnittstiteln und Summaries.

Die App reicht den gewählten Anbieter (OpenAI oder LM Studio) explizit durch.
Diese Auswahl implementiert keine vollständige agentische Baum-Tiefensuche.

Fragen mit Fehlercode gehen nicht durch die LLM-Auswahl: Der Code wird
deterministisch in den Abschnittstexten gesucht (Vorfilter). Nur wenn kein
Abschnitt den Code enthält, läuft die Auswahl über alle Abschnitte.
"""
from __future__ import annotations

import json
import os
import re
import hashlib
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

os.environ.setdefault("LM_STUDIO_API_BASE", "http://127.0.0.1:1234/v1")
os.environ.setdefault("LM_STUDIO_API_KEY", "lm-studio")

TREE_PATH = os.getenv("PAGEINDEX_TREE", str(ROOT / "pageindex_tree.json"))
MODEL = os.getenv("LOCAL_LLM_MODEL", "automatisch, falls genau ein Chatmodell geladen")
MAX_NODES = int(os.getenv("PAGEINDEX_MAX_NODES", "5"))
# Der Manual-Baum ist flach (187 ##-Abschnitte). Bei kleinem Kontextfenster wird
# die Baum-Navigation in Häppchen (Batches) mit gekürzten Summaries ausgeführt.
BATCH = int(os.getenv("PAGEINDEX_BATCH", "30"))
SUMMARY_CHARS = int(os.getenv("PAGEINDEX_SUMMARY_CHARS", "160"))

_tree = None
_node_map = None
_signature = None

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
    global _tree, _node_map, _signature
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    source = ROOT / "siemens_wissen.md"
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    if not isinstance(data, dict) or data.get("source_sha256") != digest:
        raise ValueError("PageIndex ohne gültigen Quellhash. build_pageindex_tree.py ausführen.")
    tree = data["structure"]
    mapping = {}
    def visit(nodes):
        for node in nodes:
            nid = str(node["node_id"])
            if nid in mapping:
                raise ValueError("Doppelte PageIndex node_id")
            mapping[nid] = node
            visit(node.get("nodes", []))
    visit(tree)
    _tree, _node_map = tree, mapping
    _signature = (str(Path(path).resolve()), Path(path).stat().st_mtime_ns, digest)
    return _tree


def _ensure_loaded():
    digest = hashlib.sha256((ROOT / "siemens_wissen.md").read_bytes()).hexdigest()
    signature = (str(Path(TREE_PATH).resolve()), Path(TREE_PATH).stat().st_mtime_ns, digest)
    if _tree is None or signature != _signature:
        load_tree(TREE_PATH)


def tree_available():
    try:
        _ensure_loaded()
        return True
    except (OSError, ValueError, KeyError, TypeError):
        return False


def default_complete(prompt: str, model: str | None = None) -> str:
    """Standalone-/Eval-Aufruf über den konfigurierten Standardanbieter."""
    from llm_client import make_llm
    return make_llm().complete(prompt)


def _parse_node_list(raw: str) -> list[str]:
    """Robuste Extraktion der node_list aus der LLM-Antwort."""
    txt = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip())
    try:
        data = json.loads(txt)
        ids = data.get("node_list", [])
        if isinstance(ids, list):
            return [str(x) for x in ids]
    except Exception:
        pass
    # Invalid JSON must never turn quoted explanatory numbers into evidence.
    return []


def _flat_nodes() -> list[dict]:
    """Kompakte Knotenliste {node_id, title, summary} (Summary gekürzt)."""
    out = []
    from manual_context import get_groups, group_for_text
    groups = get_groups()
    for nid, n in _node_map.items():
        summary = (n.get("summary") or n.get("title") or "").strip().replace("\n", " ")
        title = (n.get("title") or "").strip()
        group_id = group_for_text(n.get('text', ''), groups)
        if group_id:
            title = groups[group_id]['title'] + ' / ' + title
        out.append({"node_id": str(nid), "title": title[:150],
                    "summary": summary[:SUMMARY_CHARS]})
    return out


def code_candidates(query: str) -> list[str] | None:
    """Deterministischer Vorfilter: IDs der Abschnitte, deren Text einen in der
    Frage genannten Fehlercode enthält (exakter Code, kein Präfix). None, wenn
    die Frage keinen Code nennt; leere Liste, wenn kein Abschnitt ihn enthält."""
    from rag_engine import extract_error_codes
    asked = extract_error_codes(query)
    if not asked:
        return None
    hits = []
    for nid, node in _node_map.items():
        text = node.get("text", "")
        if not text.strip():
            continue
        found = asked & extract_error_codes(text)
        if found:
            hits.append((-len(found), nid))
    return [nid for _, nid in sorted(hits)]


def search(query: str, complete=None, max_nodes: int = MAX_NODES) -> list[dict]:
    """Vectorless Retrieval: LLM navigiert die Abschnitte (batch-weise) und wählt
    die relevanten aus; deren Knoten-Dicts (mit Volltext) werden zurückgegeben.
    Nennt die Frage einen Fehlercode, kommen die Abschnitte mit diesem Code ohne
    LLM-Aufruf zurück; bei mehr als max_nodes Kandidaten wählt das LLM nur unter ihnen."""
    _ensure_loaded()
    complete = complete or default_complete
    items = _flat_nodes()
    candidates = code_candidates(query)
    if candidates:
        if len(candidates) <= max_nodes:
            return [_node_map[nid] for nid in candidates]
        wanted = set(candidates)
        items = [item for item in items if item["node_id"] in wanted]
    selected: list[str] = []
    for i in range(0, len(items), BATCH):
        batch = items[i:i + BATCH]
        allowed = {n["node_id"] for n in batch}
        prompt = SEARCH_PROMPT.format(query=query, tree=json.dumps(batch, ensure_ascii=False))
        for nid in _parse_node_list(complete(prompt)):
            if nid in allowed and nid not in selected and _node_map[nid].get("text", "").strip():
                selected.append(nid)
    # Rank across batches to avoid always preferring earlier document chapters.
    if len(selected) > max_nodes:
        candidates = [n for n in items if n["node_id"] in selected]
        prompt = SEARCH_PROMPT.format(query=query, tree=json.dumps(candidates, ensure_ascii=False))
        ranked = _parse_node_list(complete(prompt))
        selected = list(dict.fromkeys(nid for nid in ranked if nid in selected))
    return [_node_map[nid] for nid in selected[:max_nodes]]


def nav_token_estimate(query: str) -> int:
    """Schätzt die Navigations-Tokens (Eingabe) ohne LLM-Aufruf — für die UI-Anzeige.
    Mit Fehlercode-Vorfilter: 0, wenn die Codeabschnitte direkt zurückkommen."""
    _ensure_loaded()
    items = _flat_nodes()
    candidates = code_candidates(query)
    if candidates:
        if len(candidates) <= MAX_NODES:
            return 0
        wanted = set(candidates)
        items = [item for item in items if item["node_id"] in wanted]
    total = 0
    for i in range(0, len(items), BATCH):
        prompt = SEARCH_PROMPT.format(query=query, tree=json.dumps(items[i:i + BATCH], ensure_ascii=False))
        try:
            import litellm
            total += litellm.token_counter(model="gpt-3.5-turbo", text=prompt)
        except Exception:
            total += len(prompt) // 4
        total += 11  # grobe Ausgabe je Navigations-Call
    return total


def retrieve_context(query: str, complete=None) -> tuple[str, list[dict]]:
    """Gibt (Kontext-Text, gewählte Knoten) für die Antwortgenerierung zurück."""
    nodes = search(query, complete=complete)
    from manual_context import expand_sources
    expanded = expand_sources([dict(n, id=n['node_id'], section=n.get('title', '')) for n in nodes])
    nodes = [dict(n, node_id=n['id'], title=n['section']) for n in expanded]
    # Whole sections can be much larger than vector chunks. Pack complete nodes
    # within the answer budget and return only evidence actually sent to the LLM.
    from rag_engine import extract_error_codes
    asked = extract_error_codes(query)
    if asked:
        nodes = sorted(nodes, key=lambda n: len(asked & extract_error_codes(n.get("text", ""))), reverse=True)
    budget = int(os.getenv("CONTEXT_MAX_CHARS", "14000"))
    selected, used = [], 0
    for node in nodes:
        text = node.get("text", "")
        if not text.strip():
            continue
        cost = len(text) + (2 if selected else 0)
        if used + cost <= budget:
            selected.append(node)
            used += cost
    if nodes and not selected:
        raise ValueError("Kein vollstaendiger PageIndex-Abschnitt passt in das Kontextbudget.")
    nodes = selected
    context = "\n\n".join(n.get("text", "") for n in nodes if n.get("text"))
    return context, nodes


def is_grounded(nodes: list[dict]) -> bool:
    """Prüft vorhandenen Text, kein semantischer Belegtreue-Nachweis."""
    return any(n.get("text", "").strip() for n in nodes)


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
        ref += " · Querverweise auf Seite " + "/".join(pages[:3])
    return ref
