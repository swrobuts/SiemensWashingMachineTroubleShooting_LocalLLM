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


def test_reranker_disabled_returns_none():
    # enable=False darf sentence-transformers NICHT importieren → hier testbar.
    assert rag_engine.get_reranker(enable=False) is None


def test_extract_error_codes_variants():
    assert rag_engine.extract_error_codes("Was bedeutet E:18?") == {"E:18", "E18"}
    assert rag_engine.extract_error_codes("meine Maschine zeigt E23") == {"E:23", "E23"}
    assert rag_engine.extract_error_codes("Fehler 18 im Display") == {"E:18", "E18"}
    assert rag_engine.extract_error_codes("Fehlercode 23") == {"E:23", "E23"}


def test_extract_error_codes_none():
    assert rag_engine.extract_error_codes("Wasser läuft aus") == set()
    assert rag_engine.extract_error_codes("") == set()


class _StubNode:
    def __init__(self, text):
        self._t = text

    def get_content(self):
        return self._t


class _StubSN:
    def __init__(self, text):
        self.node = _StubNode(text)


def test_format_source_reference_heading_and_pages():
    sns = [_StubSN("## Hinweise im Anzeigefeld\nAnzeige: E:18; Abhilfe: Laugenpumpe reinigen. ~ Seite 30")]
    ref = rag_engine.format_source_reference(sns)
    assert "Hinweise im Anzeigefeld" in ref
    assert "Seite 30" in ref


def test_format_source_reference_empty():
    assert rag_engine.format_source_reference([]) == "Siemens Handbuch"


class _ScoredNode:
    node = None

    def __init__(self, score):
        self.score = score


def test_is_grounded_threshold():
    # Kalibriert: In-Scope ≥ 0.435, Out-of-Scope ~0.0, Default-Schwelle 0.15.
    assert rag_engine.is_grounded([_ScoredNode(0.44)])
    assert rag_engine.is_grounded([_ScoredNode(0.90)])
    assert not rag_engine.is_grounded([_ScoredNode(0.0)])
    assert not rag_engine.is_grounded([])


def test_is_grounded_custom_threshold():
    assert rag_engine.is_grounded([_ScoredNode(0.9)], min_score=0.5)
    assert not rag_engine.is_grounded([_ScoredNode(0.3)], min_score=0.5)


def test_top_relevance_handles_missing():
    assert rag_engine.top_relevance([]) == 0.0
    assert rag_engine.top_relevance([_ScoredNode(None)]) == 0.0
    assert rag_engine.top_relevance([_ScoredNode(0.7)]) == 0.7


def test_code_boundaries():
    assert rag_engine.extract_error_codes('E:18') != rag_engine.extract_error_codes('E:180')
    assert rag_engine.extract_error_codes('e : 18') == {'E:18','E18'}
    assert rag_engine.extract_error_codes('Fehlercode: 23') == {'E:23','E23'}


def test_cache_includes_chunk_configuration(tmp_path):
    md = _write(tmp_path, 'test')
    assert rag_engine.compute_cache_key(md,'model',chunk_tokens=400) != rag_engine.compute_cache_key(md,'model',chunk_tokens=440)


def test_cosine_is_not_treated_as_reranker_confidence():
    n = _ScoredNode(0.99)
    assert not rag_engine.is_grounded([n],reranked=False)


def test_cross_reference_is_not_source_page():
    ref = rag_engine.format_source_reference([_StubSN('## E:23\nKundendienst ~ Seite 36')])
    assert 'Querverweise auf Seite 36' in ref
    assert 'PDF-Seite' not in ref


def test_multiple_tables_and_continuation_rows():
    from llama_index.core.schema import TextNode
    text = '## Störungen\n| Fehler | Hilfe |\n|---|---|\n| E:18 | Pumpe |\n| | Schlauch |\n\nText zwischen Tabellen\n\n| Signal | Aktion |\n|---|---|\n| E:23 | Wasserhahn |'
    nodes = rag_engine._explode_markdown_tables([TextNode(text=text)], max_chars=1)
    texts = [n.text for n in nodes]
    assert any('Fehler: E:18; Hilfe: Schlauch' in t for t in texts)
    assert any('Signal: E:23; Aktion: Wasserhahn' in t for t in texts)
    assert any('Text zwischen Tabellen' in t for t in texts)


def test_hybrid_exact_match_is_first_without_mutation():
    from llama_index.core.schema import TextNode, NodeWithScore
    from types import SimpleNamespace as NS
    exact, wrong = TextNode(text='E:18 Laugenpumpe'), TextNode(text='E:180 anderes Problem')
    index = NS(docstore=NS(docs={exact.node_id:exact,wrong.node_id:wrong}),
               as_retriever=lambda **_:NS(retrieve=lambda _: [NodeWithScore(node=wrong,score=0.9)]))
    nodes = rag_engine.make_retriever(index).retrieve('Fehler E18')
    assert nodes[0].node.node_id == exact.node_id
    assert 'exact_code_match' not in exact.metadata
    assert not nodes[1].node.metadata.get('exact_code_match')


def test_true_page_provenance(tmp_path):
    path=_write(tmp_path,'<!-- pdf-page: 4 -->\n## Hinweise\nE:23 Kundendienst auf Seite 36.')
    nodes=rag_engine.prepare_nodes(path)
    assert nodes[0].metadata['pdf_page']==4
    from llama_index.core.schema import NodeWithScore
    ref=rag_engine.format_source_reference([NodeWithScore(node=nodes[0],score=1)])
    assert 'PDF-Seite 4' in ref and '36' not in ref
