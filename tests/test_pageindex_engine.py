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
