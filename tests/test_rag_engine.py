"""Tests für die reine Logik in rag_engine (ohne llama_index / torch).

rag_engine importiert die schweren Abhängigkeiten *lazy*, daher lässt sich
compute_cache_key hier ohne installiertes LlamaIndex testen.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import rag_engine


def _write(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "wissen.md"
    p.write_text(content, encoding="utf-8")
    return p


def test_cache_key_is_deterministic(tmp_path):
    md = _write(tmp_path, "# Titel\nInhalt")
    k1 = rag_engine.compute_cache_key(md, "intfloat/multilingual-e5-small")
    k2 = rag_engine.compute_cache_key(md, "intfloat/multilingual-e5-small")
    assert k1 == k2


def test_cache_key_changes_with_content(tmp_path):
    md = _write(tmp_path, "Version A")
    k1 = rag_engine.compute_cache_key(md, "modelX")
    md.write_text("Version B", encoding="utf-8")
    k2 = rag_engine.compute_cache_key(md, "modelX")
    assert k1 != k2


def test_cache_key_changes_with_embed_model(tmp_path):
    md = _write(tmp_path, "gleicher Inhalt")
    k1 = rag_engine.compute_cache_key(md, "intfloat/multilingual-e5-small")
    k2 = rag_engine.compute_cache_key(md, "intfloat/multilingual-e5-base")
    assert k1 != k2


def test_cache_key_changes_with_parser_version(tmp_path):
    md = _write(tmp_path, "gleicher Inhalt")
    k1 = rag_engine.compute_cache_key(md, "modelX", parser_version="md-v1")
    k2 = rag_engine.compute_cache_key(md, "modelX", parser_version="md-v2")
    assert k1 != k2


def test_e5_needs_prefix():
    assert rag_engine._needs_e5_prefix("intfloat/multilingual-e5-small")
    assert rag_engine._needs_e5_prefix("intfloat/multilingual-e5-base")


def test_non_e5_no_prefix():
    assert not rag_engine._needs_e5_prefix("BAAI/bge-m3")
    assert not rag_engine._needs_e5_prefix("sentence-transformers/all-MiniLM-L6-v2")
