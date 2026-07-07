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
import os
from pathlib import Path

# Embedding-Modell — per ENV umstellbar (Phase 1: e5-base / bge-m3).
DEFAULT_EMBED_MODEL = os.getenv("EMBED_MODEL", "intfloat/multilingual-e5-small")

# Version der Chunking-/Node-Logik. Erhöhen, wenn sich der Parser ändert, damit
# ein alter persistenter Index automatisch verworfen und neu gebaut wird.
PARSER_VERSION = "md-v1"

DEFAULT_MD_PATH = "siemens_wissen.md"
DEFAULT_PERSIST_DIR = "storage"

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


def _needs_e5_prefix(model_name: str) -> bool:
    """e5-Modelle verlangen ``query:``/``passage:``-Präfixe (asymmetrisches Training)."""
    return "e5" in model_name.lower()


def compute_cache_key(
    md_path: str | Path,
    embed_model: str,
    parser_version: str = PARSER_VERSION,
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
    return h.hexdigest()


def get_embed_model(model_name: str = DEFAULT_EMBED_MODEL):
    """Lokales HuggingFace-Embedding. Für e5-Modelle die nötigen Präfixe setzen.

    Ohne diese Präfixe liefert e5 deutlich schlechtere Treffer — das war der
    größte Retrieval-Bug der Ausgangsversion.
    """
    from llama_index.embeddings.huggingface import HuggingFaceEmbedding

    kwargs: dict = {"model_name": model_name}
    if _needs_e5_prefix(model_name):
        kwargs["query_instruction"] = "query: "
        kwargs["text_instruction"] = "passage: "
    return HuggingFaceEmbedding(**kwargs)


def get_reranker(model_name: str | None = None, top_n: int | None = None, enable: bool | None = None):
    """Cross-Encoder-Reranker (oder ``None``, wenn deaktiviert).

    Bei ``enable=False`` wird ``sentence-transformers`` gar nicht erst geladen —
    so bleibt die Funktion ohne schwere Abhängigkeiten testbar.
    """
    enable = ENABLE_RERANK if enable is None else enable
    if not enable:
        return None
    from llama_index.core.postprocessor import SentenceTransformerRerank

    return SentenceTransformerRerank(
        model=model_name or RERANK_MODEL,
        top_n=top_n or FINAL_K,
    )


def build_or_load_index(
    md_path: str | Path = DEFAULT_MD_PATH,
    persist_dir: str | Path = DEFAULT_PERSIST_DIR,
    embed_model_name: str = DEFAULT_EMBED_MODEL,
):
    """Persistenten Index laden, wenn Quelle+Konfig unverändert; sonst neu bauen.

    Setzt ``Settings.embed_model``. Der aufrufende Server setzt zusätzlich
    ``Settings.llm`` (das Eval braucht kein LLM).
    """
    from llama_index.core import (
        Settings,
        SimpleDirectoryReader,
        StorageContext,
        VectorStoreIndex,
        load_index_from_storage,
    )
    from llama_index.core.node_parser import MarkdownNodeParser

    persist_dir = Path(persist_dir)
    key_file = persist_dir / ".cache_key"
    cache_key = compute_cache_key(md_path, embed_model_name)

    # Wichtig: gleiches Embedding-Modell vor dem Laden setzen wie beim Bauen.
    Settings.embed_model = get_embed_model(embed_model_name)

    if key_file.exists() and key_file.read_text(encoding="utf-8").strip() == cache_key:
        print(f"♻️  Lade persistenten Index aus '{persist_dir}' (Cache-Treffer).")
        storage_context = StorageContext.from_defaults(persist_dir=str(persist_dir))
        return load_index_from_storage(storage_context)

    print(f"🔧 Baue Index neu (Quelle/Konfig geändert) → '{persist_dir}' …")
    documents = SimpleDirectoryReader(input_files=[str(md_path)]).load_data()
    nodes = MarkdownNodeParser().get_nodes_from_documents(documents)
    index = VectorStoreIndex(nodes)
    persist_dir.mkdir(parents=True, exist_ok=True)
    index.storage_context.persist(persist_dir=str(persist_dir))
    key_file.write_text(cache_key, encoding="utf-8")
    print(f"✅ Index gebaut & persistiert ({len(nodes)} Abschnitte).")
    return index
