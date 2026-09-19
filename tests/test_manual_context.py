from pathlib import Path
import manual_context as mc
import rag_engine


def test_pump_fragment_includes_safety_and_no_transport_steps():
    fragment = '## 3. Service-Klappe öffnen und abnehmen.'
    result = mc.expand_sources([{'id':'part','section':'Service-Klappe','text':fragment}])
    assert len(result) == 1
    text = result[0]['text']
    assert 'Waschlauge abkühlen' in text
    assert 'Netzstecker ziehen' in text
    assert 'Wasserhahn schließen' in text
    assert 'Schläuche abmontieren' not in text


def test_procedure_expansion_keeps_source_text_and_deduplicates():
    group = mc.get_groups()['pump']
    sources = [{'id':'a','text':'fragment','context_group':'pump'},
               {'id':'b','text':'other','context_group':'pump'}]
    result = mc.expand_sources(sources)
    assert len(result) == 1 and result[0]['text'] == group['text']
    assert group['text'] in mc.MANUAL.read_text(encoding='utf-8')


def test_transport_scope_survives_chunking():
    nodes = rag_engine.prepare_nodes(mc.MANUAL)
    transport = [n for n in nodes if 'Schläuche abmontieren' in n.text]
    assert transport
    assert all(n.metadata['context_group'] == 'transport' for n in transport)
    assert all('Transportieren' in n.metadata['section'] for n in transport)


def test_all_pump_fragments_carry_context_group():
    nodes = rag_engine.prepare_nodes(mc.MANUAL)
    fragments = [n for n in nodes if 'Service-Klappe öffnen' in n.text or
                 'Lassen Sie die Waschlauge abkühlen.' in n.text]
    assert len(fragments) >= 2
    assert all(n.metadata.get('context_group') == 'pump' for n in fragments)
