import json
import pytest
import pageindex_engine as pe


def test_invalid_json_is_not_evidence():
    assert pe._parse_node_list('I thought about "0123" but cannot answer') == []
    assert pe._parse_node_list('```json\n{"node_list":["0123"]}\n```') == ['0123']


def test_empty_text_is_not_grounded():
    assert not pe.is_grounded([{'node_id':'0001','text':''}])


def test_cross_batch_selection_is_rejected(monkeypatch):
    monkeypatch.setattr(pe, '_ensure_loaded', lambda: None)
    monkeypatch.setattr(pe, 'BATCH', 1)
    monkeypatch.setattr(pe, '_node_map', {'0001':{'node_id':'0001','title':'A','text':'A'},
                                        '0002':{'node_id':'0002','title':'B','text':'B'}})
    responses = iter(['{"node_list":["0002"]}', '{"node_list":[]}'])
    assert pe.search('test',complete=lambda _: next(responses)) == []


def test_final_ranking_removes_document_order_bias(monkeypatch):
    monkeypatch.setattr(pe, '_ensure_loaded', lambda: None)
    monkeypatch.setattr(pe, 'BATCH', 1)
    monkeypatch.setattr(pe, '_node_map', {k:{'node_id':k,'title':k,'text':k} for k in ['0001','0002']})
    responses = iter(['{"node_list":["0001"]}', '{"node_list":["0002"]}', '{"node_list":["0002","0001"]}'])
    assert pe.search('test',complete=lambda _:next(responses),max_nodes=1)[0]['node_id'] == '0002'


def test_stale_tree_refused(tmp_path):
    path=tmp_path/'tree.json'
    path.write_text(json.dumps({'source_sha256':'wrong','structure':[]}),encoding='utf-8')
    with pytest.raises(ValueError):
        pe.load_tree(path)


def test_context_budget_keeps_complete_sections_and_matching_sources(monkeypatch):
    nodes = [{'node_id':'1','text':'abcdefgh'}, {'node_id':'2','text':'12345678'},
             {'node_id':'3','text':'xyz'}]
    monkeypatch.setattr(pe, 'search', lambda *a, **kw: nodes)
    monkeypatch.setenv('CONTEXT_MAX_CHARS', '13')
    context, sources = pe.retrieve_context('Waschmaschine')
    assert context == 'abcdefgh\n\nxyz'
    assert [n['node_id'] for n in sources] == ['1','3']
    assert len(context) <= 13


def test_context_budget_prioritizes_exact_code_not_prefix(monkeypatch):
    nodes = [{'node_id':'1','text':'E:180 sonstiges'},
             {'node_id':'2','text':'E:18 Pumpe'}]
    monkeypatch.setattr(pe, 'search', lambda *a, **kw: nodes)
    monkeypatch.setenv('CONTEXT_MAX_CHARS', '16')
    context, sources = pe.retrieve_context('Was bedeutet E:18?')
    assert context == 'E:18 Pumpe'
    assert [n['node_id'] for n in sources] == ['2']


def test_oversized_section_is_not_silently_cut_or_reported_missing(monkeypatch):
    monkeypatch.setattr(pe, 'search', lambda *a, **kw: [{'node_id':'1','text':'Long source'}])
    monkeypatch.setenv('CONTEXT_MAX_CHARS', '5')
    with pytest.raises(ValueError, match='Kontextbudget'):
        pe.retrieve_context('Waschmaschine')


def test_real_manual_error_tables_fit_together_only_after_packing(monkeypatch):
    pe.load_tree()
    nodes = [pe._node_map['0126'], pe._node_map['0125']]
    monkeypatch.setattr(pe, 'search', lambda *a, **kw: nodes)
    monkeypatch.setenv('CONTEXT_MAX_CHARS', '14000')
    assert sum(len(n['text']) for n in nodes) > 14000
    context, sources = pe.retrieve_context('Was bedeutet E:23?')
    assert 'E:23' in context and len(context) <= 14000
    assert [n['node_id'] for n in sources] == ['0125']


def test_error_code_prefilter_returns_code_sections_without_llm(monkeypatch):
    monkeypatch.setattr(pe, '_ensure_loaded', lambda: None)
    monkeypatch.setattr(pe, '_node_map', {'0001': {'node_id': '0001', 'title': 'A', 'text': 'E:180 sonstiges'},
                                          '0002': {'node_id': '0002', 'title': 'B', 'text': 'E:18 Laugenpumpe'},
                                          '0003': {'node_id': '0003', 'title': 'C', 'text': 'Trommel reinigen'}})
    def no_llm(_):
        raise AssertionError('LLM darf bei Fehlercode-Treffern nicht aufgerufen werden')
    assert [n['node_id'] for n in pe.search('Was bedeutet E:18?', complete=no_llm)] == ['0002']
    assert pe.nav_token_estimate('Was bedeutet E:18?') == 0


def test_error_code_prefilter_falls_back_to_navigation_when_code_unknown(monkeypatch):
    monkeypatch.setattr(pe, '_ensure_loaded', lambda: None)
    monkeypatch.setattr(pe, 'BATCH', 5)
    monkeypatch.setattr(pe, '_node_map', {'0001': {'node_id': '0001', 'title': 'A', 'text': 'Trommel'},
                                          '0002': {'node_id': '0002', 'title': 'B', 'text': 'Pumpe'}})
    calls = []
    def complete(prompt):
        calls.append(prompt)
        return '{"node_list":["0002"]}'
    assert [n['node_id'] for n in pe.search('Was bedeutet E:99?', complete=complete)] == ['0002']
    assert len(calls) == 1 and '0001' in calls[0]


def test_error_code_prefilter_navigates_only_within_candidates(monkeypatch):
    monkeypatch.setattr(pe, '_ensure_loaded', lambda: None)
    monkeypatch.setattr(pe, 'BATCH', 10)
    nodes = {f'{i:04d}': {'node_id': f'{i:04d}', 'title': f'T{i}', 'text': 'E:23 Bodenwanne'} for i in range(1, 8)}
    nodes['0009'] = {'node_id': '0009', 'title': 'Anderes', 'text': 'Trommel'}
    monkeypatch.setattr(pe, '_node_map', nodes)
    prompts = []
    def complete(prompt):
        prompts.append(prompt)
        return '{"node_list":["0003"]}'
    assert [n['node_id'] for n in pe.search('E:23?', complete=complete, max_nodes=5)] == ['0003']
    assert all('0009' not in p for p in prompts)
