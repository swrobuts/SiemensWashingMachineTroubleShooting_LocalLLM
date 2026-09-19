"""RAG-Infrastruktur: lokale Embeddings + persistenter Vektorindex.

Bewusst getrennt von Flask/LLM (server.py), damit das Eval-Set den Retriever
ohne laufendes LM Studio testen kann — Retrieval braucht nur das Embedding-
Modell, nicht das Antwort-LLM.

Schwere Importe (llama_index, torch) sind absichtlich *lazy* (innerhalb der
Funktionen), damit reine Logik wie ``compute_cache_key`` ohne diese
Abhängigkeiten importier- und testbar bleibt.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

# Embedding-Modell — per ENV umstellbar (Phase 1: e5-base / bge-m3).
DEFAULT_EMBED_MODEL = os.getenv("EMBED_MODEL", "intfloat/multilingual-e5-small")

# Version der Chunking-/Node-Logik. Erhöhen, wenn sich der Parser ändert, damit
# ein alter persistenter Index automatisch verworfen und neu gebaut wird.
PARSER_VERSION = "md-v4-token-bounded"

# Große Markdown-Tabellen (z. B. die Fehlercode-Tabelle, ~6 KB) embedden als
# unspezifischer „Brei" und werden für konkrete Fragen nicht gefunden. Solche
# Nodes werden zeilenweise aufgeteilt — jede Tabellenzeile (jeder Fehlercode)
# wird ein eigener, auffindbarer Abschnitt mit Überschrift + Tabellenkopf.
MAX_NODE_CHARS = int(os.getenv("MAX_NODE_CHARS", "1600"))

DEFAULT_MD_PATH = ROOT / "siemens_wissen.md"
DEFAULT_PERSIST_DIR = ROOT / "storage"
CHUNK_TOKENS = int(os.getenv("CHUNK_TOKENS", "440"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "40"))

# Zweistufiges Retrieval: erst breit per Vektor abrufen (RETRIEVE_K), dann per
# Cross-Encoder auf die wirklich relevanten FINAL_K herunter-reranken. Der
# Reranker liest Frage + Textstück gemeinsam und ist deutlich präziser als reine
# Vektorähnlichkeit — genau das hebt die Trefferqualität.
RETRIEVE_K = int(os.getenv("RETRIEVE_K", "12"))   # Overfetch für den Reranker
FINAL_K = int(os.getenv("FINAL_K", "5"))          # was das LLM am Ende sieht

# Multilingualer Reranker (versteht Deutsch gut). Leichtere Alternative:
# "cross-encoder/ms-marco-MiniLM-L6-v2" (schneller, aber englisch-lastig).
RERANK_MODEL = os.getenv("RERANK_MODEL", "BAAI/bge-reranker-v2-m3")
ENABLE_RERANK = os.getenv("ENABLE_RERANK", "1") != "0"

# Relevanzfilter: explizite Sigmoid-Scores in [0,1], keine Wahrheitswahrscheinlichkeit.
# Die Schwelle ist ein Projektparameter und braucht ein größeres annotiertes Evalset.
GUARDRAIL_MIN_SCORE = float(os.getenv("GUARDRAIL_MIN_SCORE", "0.15"))

# Antwort, wenn die Frage nicht durch das Handbuch gedeckt ist (kein LLM-Aufruf).
NOT_IN_MANUAL = (
    "Dazu finde ich in dieser Bedienungsanleitung leider keine Information. "
    "Bitte formulieren Sie Ihre Frage zur Waschmaschine anders oder wenden Sie "
    "sich an den Siemens-Kundendienst."
)


def top_relevance(nodes) -> float:
    """Reranker-Score des besten Treffers (0.0, wenn keine Knoten)."""
    if not nodes or nodes[0].score is None:
        return 0.0
    return float(nodes[0].score)


def is_grounded(nodes, min_score: float | None = None, *, reranked: bool = True) -> bool:
    """True, wenn der beste Treffer relevant genug ist (Frage vom Handbuch gedeckt)."""
    # Cosine similarities and cross-encoder scores have different scales.
    # Without a calibrated reranker, only an exact error-code match passes.
    if not reranked and min_score is None:
        return any(getattr(n.node, "metadata", {}).get("exact_code_match") for n in nodes)
    thr = GUARDRAIL_MIN_SCORE if min_score is None else min_score
    score = top_relevance(nodes)
    return bool(nodes) and math.isfinite(score) and score >= thr

# Fehlercodes (E:18, E18, "Fehler 18") aus der Frage ziehen. Dense-Retrieval
# findet solche seltenen Codes unzuverlässig — deshalb holt der Hybrid-Retriever
# den exakt passenden Chunk zusätzlich per Schlüsselwort dazu.
_CODE_RE = re.compile(r"(?:\bE\s*:?\s*|\bfehler(?:code)?\s*:?\s*)(\d{1,3})\b", re.IGNORECASE)


def extract_error_codes(query: str) -> set[str]:
    """Liefert Suchvarianten je erkanntem Code, z. B. {'E:18', 'E18'}."""
    codes: set[str] = set()
    for m in _CODE_RE.finditer(query or ""):
        n = m.group(1)
        codes.add(f"E:{n}")
        codes.add(f"E{n}")
    return codes


def _needs_e5_prefix(model_name: str) -> bool:
    """e5-Modelle verlangen ``query:``/``passage:``-Präfixe (asymmetrisches Training)."""
    return "e5" in model_name.lower()


def compute_cache_key(
    md_path: str | Path,
    embed_model: str,
    parser_version: str = PARSER_VERSION,
    *, max_node_chars: int = MAX_NODE_CHARS, chunk_tokens: int = CHUNK_TOKENS,
    chunk_overlap: int = CHUNK_OVERLAP,
) -> str:
    """Stabiler Schlüssel aus Quelldatei-Inhalt + Embedding-Modell + Parser-Version.

    Ändert sich eines davon, unterscheidet sich der Schlüssel und der persistente
    Index wird neu gebaut. So kann ein alter Index (z. B. mit falschem Modell oder
    ohne e5-Präfixe) niemals „falsch positiv" wiederverwendet werden.
    """
    h = hashlib.sha256()
    h.update(Path(md_path).read_bytes())
    h.update(b"\x00")
    h.update(embed_model.encode("utf-8"))
    h.update(b"\x00")
    h.update(parser_version.encode("utf-8"))
    h.update(json.dumps([max_node_chars, chunk_tokens, chunk_overlap, "e5-prefix-v1"]).encode())
    return h.hexdigest()


def get_embed_model(model_name: str = DEFAULT_EMBED_MODEL):
    """Lokales HuggingFace-Embedding. Für e5-Modelle die nötigen Präfixe setzen.

    Ohne diese Präfixe liefert e5 deutlich schlechtere Treffer — das war der
    größte Retrieval-Bug der Ausgangsversion.
    """
    from llama_index.embeddings.huggingface import HuggingFaceEmbedding

    kwargs: dict = {"model_name": model_name, "cache_folder": str(ROOT / ".cache" / "embeddings")}
    if _needs_e5_prefix(model_name):
        kwargs["query_instruction"] = "query: "
        kwargs["text_instruction"] = "passage: "
    return HuggingFaceEmbedding(**kwargs)


def _explode_markdown_tables(nodes, max_chars: int = MAX_NODE_CHARS):
    """Große tabellenlastige Nodes zeilenweise aufteilen.

    Jede Datenzeile wird ein eigener Node aus ``Überschrift + Tabellenkopf + Zeile``,
    sodass z. B. ``E:18 | Laugenpumpe verstopft …`` gezielt auffindbar wird.
    Kleine Nodes und Nodes ohne echte Tabelle bleiben unverändert. Kein Inhalt
    geht verloren (Fließtext-Anteile werden als eigener Node behalten).
    """
    from llama_index.core.schema import TextNode

    out = []
    for node in nodes:
        text = node.get_content()
        table_lines = [l for l in text.split("\n") if l.strip().startswith("|")]
        # Nur echte, große Tabellen aufteilen (Kopf + Trennzeile + ≥1 Datenzeile).
        if len(text) <= max_chars or len(table_lines) < 3:
            out.append(node)
            continue

        lines = text.split("\n")
        heading = " ".join(l.strip() for l in lines if l.strip().startswith("#"))
        prose = "\n".join(
            l for l in lines
            if l.strip() and not l.strip().startswith("|") and not l.strip().startswith("#")
        ).strip()
        if prose:
            out.append(TextNode(text=f"{heading}\n{prose}".strip(), metadata=dict(node.metadata)))
        # Parse each contiguous table separately, preserving its own header.
        for block in re.findall(r"(?:^[ \t]*\|.*(?:\n|$))+", text, re.MULTILINE):
            rows = block.strip().splitlines()
            if len(rows) < 3 or not re.fullmatch(r"[|\s:\-]+", rows[1]):
                out.append(TextNode(text=f"{heading}\n{block}".strip(), metadata=dict(node.metadata)))
                continue
            labels = _split_row(rows[0])
            previous_subject = ""
            for row in rows[2:]:
                cells = _split_row(row)
                if not any(cells):
                    continue
                if cells[0]:
                    previous_subject = cells[0]
                elif previous_subject:
                    cells[0] = previous_subject
                pairs = "; ".join(f"{lbl}: {val}" if lbl else val
                                  for lbl, val in zip(labels + [""] * len(cells), cells) if val)
                out.append(TextNode(text=f"{heading}\n{pairs}".strip(), metadata=dict(node.metadata)))
    return out


def _split_row(line: str) -> list[str]:
    """Markdown-Tabellenzeile in bereinigte Zellen zerlegen (Whitespace kollabiert)."""
    return [re.sub(r"\s+", " ", c).replace(r"\|", "|").strip()
            for c in re.split(r"(?<!\\)\|", line.strip().strip("|"))]


def get_reranker(model_name: str | None = None, top_n: int | None = None, enable: bool | None = None):
    """Cross-Encoder-Reranker (oder ``None``, wenn deaktiviert).

    Bei ``enable=False`` wird ``sentence-transformers`` gar nicht erst geladen —
    so bleibt die Funktion ohne schwere Abhängigkeiten testbar.
    """
    enable = ENABLE_RERANK if enable is None else enable
    if not enable:
        return None
    from llama_index.core.postprocessor import SentenceTransformerRerank
    import torch

    reranker = SentenceTransformerRerank(model=model_name or RERANK_MODEL,
                                        top_n=top_n or FINAL_K, trust_remote_code=False)
    # BGE returns logits by default. Explicit sigmoid makes our threshold scale
    # independent of model-card / sentence-transformers defaults.
    reranker._model.activation_fn = torch.nn.Sigmoid()
    return reranker


def prepare_nodes(md_path=DEFAULT_MD_PATH, tokenizer=None):
    """Parse headings/tables and bound chunks using the embedding tokenizer."""
    from llama_index.core import Document
    from llama_index.core.node_parser import MarkdownNodeParser, SentenceSplitter
    from llama_index.core.schema import TextNode
    raw = Path(md_path).read_text(encoding="utf-8")
    # New parser exports physical PDF page markers. Legacy Markdown has none.
    parts = re.split(r"<!-- pdf-page: (\d+) -->", raw)
    documents = []
    if parts[0].strip():
        documents.append(Document(text=parts[0], metadata={"file_name": Path(md_path).name}))
    for i in range(1, len(parts), 2):
        documents.append(Document(text=parts[i + 1], metadata={"file_name": Path(md_path).name,
                                                               "pdf_page": int(parts[i])}))
    nodes = _explode_markdown_tables(MarkdownNodeParser().get_nodes_from_documents(documents))
    splitter = SentenceSplitter(chunk_size=CHUNK_TOKENS, chunk_overlap=CHUNK_OVERLAP,
                                tokenizer=tokenizer)
    result = []
    for node in nodes:
        heading = next((l.lstrip("# ") for l in node.text.splitlines() if l.startswith("#")), "")
        metadata = dict(node.metadata, section=heading)
        for part in splitter.split_text(node.text):
            result.append(TextNode(text=part, metadata=metadata,
                                   excluded_embed_metadata_keys=list(metadata),
                                   excluded_llm_metadata_keys=list(metadata)))
    return result


def build_or_load_index(
    md_path: str | Path = DEFAULT_MD_PATH,
    persist_dir: str | Path = DEFAULT_PERSIST_DIR,
    embed_model_name: str = DEFAULT_EMBED_MODEL,
):
    from filelock import FileLock
    persist_dir = Path(persist_dir)
    persist_dir.mkdir(parents=True, exist_ok=True)
    with FileLock(str(persist_dir / ".build.lock"), timeout=600):
        return _build_or_load_index(md_path, persist_dir, embed_model_name)


def _build_or_load_index(md_path, persist_dir, embed_model_name):
    """Persistenten Index laden, wenn Quelle+Konfig unverändert; sonst neu bauen.

    Setzt ``Settings.embed_model``. Der aufrufende Server setzt zusätzlich
    ``Settings.llm`` (das Eval braucht kein LLM).
    """
    from llama_index.core import (
        Settings,
        StorageContext,
        VectorStoreIndex,
        load_index_from_storage,
    )

    persist_dir = Path(persist_dir)
    key_file = persist_dir / ".cache_key"
    cache_key = compute_cache_key(md_path, embed_model_name)

    # Wichtig: gleiches Embedding-Modell vor dem Laden setzen wie beim Bauen.
    embed_model = get_embed_model(embed_model_name)
    limit = embed_model._model.max_seq_length
    if not 0 <= CHUNK_OVERLAP < CHUNK_TOKENS < limit - 8:
        raise ValueError(f"CHUNK_TOKENS muss unter {limit - 8} liegen; Overlap kleiner als Chunk.")
    Settings.embed_model = embed_model

    if key_file.exists() and key_file.read_text(encoding="utf-8").strip() == cache_key:
        print(f"♻️  Lade persistenten Index aus '{persist_dir}' (Cache-Treffer).")
        try:
            storage_context = StorageContext.from_defaults(persist_dir=str(persist_dir))
            return load_index_from_storage(storage_context, embed_model=embed_model)
        except (OSError, ValueError, KeyError):
            print("Unvollständiger Index-Cache; Index wird neu erstellt.")

    print(f"🔧 Baue Index neu (Quelle/Konfig geändert) → '{persist_dir}' …")
    tokenizer = embed_model._model.tokenizer
    nodes = prepare_nodes(md_path, tokenizer=lambda t: tokenizer.encode(t, add_special_tokens=False))
    index = VectorStoreIndex(nodes, embed_model=embed_model)
    persist_dir.mkdir(parents=True, exist_ok=True)
    index.storage_context.persist(persist_dir=str(persist_dir))
    key_file.write_text(cache_key, encoding="utf-8")
    print(f"✅ Index gebaut & persistiert ({len(nodes)} Abschnitte).")
    return index


def make_retriever(index, vector_k: int = RETRIEVE_K, *, hybrid: bool = True):
    """Hybrider Retriever: Vektor-Overfetch + garantierte Fehlercode-Chunks.

    Enthält die Frage einen Fehlercode (E:18 …), werden alle Chunks mit genau
    diesem Code zusätzlich ins Kandidatenset gelegt — so kann der Reranker sie
    hochziehen, statt dass dense Retrieval sie verpasst.
    """
    from llama_index.core.retrievers import BaseRetriever
    from llama_index.core.schema import NodeWithScore

    class _HybridRetriever(BaseRetriever):
        def __init__(self):
            self._vr = index.as_retriever(similarity_top_k=vector_k)
            self._docs = index.docstore.docs
            super().__init__()

        def _retrieve(self, query_bundle):
            nodes = self._vr.retrieve(query_bundle)
            codes = extract_error_codes(query_bundle.query_str) if hybrid else set()
            if not codes:
                return nodes
            exact = []
            have = set()
            for nid, node in self._docs.items():
                content = node.get_content()
                if codes & extract_error_codes(content):
                    # Copy: a per-request match must never contaminate the stored node.
                    matched = node.model_copy(deep=True)
                    matched.metadata["exact_code_match"] = True
                    matched.excluded_embed_metadata_keys.append("exact_code_match")
                    exact.append(NodeWithScore(node=matched, score=1.0))
                    have.add(nid)
            return exact + [n for n in nodes if n.node.node_id not in have]

    return _HybridRetriever()


_PAGE_RE = re.compile(r"Seite\s+(\d{1,3})")


def format_source_reference(source_nodes, max_pages: int = 3) -> str:
    """Baut eine echte Quellenangabe aus den genutzten Chunks: Abschnitt + Seite(n).

    Nutzt die ``~ Seite NN``-Verweise aus dem Handbuch. Verhindert die bisher
    hart verdrahtete Pseudo-Referenz und macht Antworten überprüfbar.
    """
    if not source_nodes:
        return "Siemens Handbuch"
    heading = getattr(source_nodes[0].node, "metadata", {}).get("section", "")
    for line in source_nodes[0].node.get_content().split("\n"):
        s = line.strip()
        if s.startswith("#"):
            heading = s.lstrip("# ").strip()
            break
    pages = list(dict.fromkeys(str(n.node.metadata["pdf_page"]) for n in source_nodes
                              if getattr(n.node, "metadata", {}).get("pdf_page")))
    cross_refs: list[str] = []
    for sn in source_nodes[:max_pages]:
        for m in _PAGE_RE.finditer(sn.node.get_content()):
            if m.group(1) not in cross_refs:
                cross_refs.append(m.group(1))
    ref = "Handbuch"
    if heading:
        ref += f": {heading}"
    if pages:
        ref += " · PDF-Seite " + "/".join(pages[:max_pages])
    elif cross_refs:
        ref += " · Querverweise auf Seite " + "/".join(cross_refs[:max_pages])
    return ref


def make_query_engine(index, qa_template=None):
    """Blockierende Query-Engine mit Hybrid-Retriever + Reranker (für /api/ask).

    Hinweis: Für echtes Token-Streaming NICHT den Streaming-Modus dieser Engine
    nutzen — der puffert und liefert erst am Ende alles auf einmal. server.py
    streamt stattdessen das LLM direkt (siehe /api/ask_stream).
    """
    from llama_index.core.query_engine import RetrieverQueryEngine

    reranker = get_reranker()
    engine = RetrieverQueryEngine.from_args(
        make_retriever(index),
        node_postprocessors=[reranker] if reranker else [],
    )
    if qa_template is not None:
        engine.update_prompts({"response_synthesizer:text_qa_template": qa_template})
    return engine
