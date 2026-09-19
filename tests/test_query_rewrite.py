import json
from types import SimpleNamespace as NS
import pytest
import server


def backend(monkeypatch, replies, rewritten='{"query":"Wasser läuft aus"}'):
    service = server.Backend()
    service._retriever = NS(retrieve=lambda _: [])
    searches, prompts, providers, closed = [], [], [], []
    def search(question):
        searches.append(question)
        return replies[min(len(searches) - 1, len(replies) - 1)]
    def complete(prompt):
        prompts.append(prompt)
        if isinstance(rewritten, Exception):
            raise rewritten
        return rewritten
    def llm(provider=None, api_key=None):
        providers.append((provider, api_key))
        return NS(complete=complete, client=NS(close=lambda: closed.append(True)))
    monkeypatch.setattr(service, '_retrieve_hybrid', search, raising=False)
    monkeypatch.setattr(service, 'llm', llm)
    return service, searches, prompts, providers, closed


MISS = server.Retrieval('', False, '', [])
HIT = server.Retrieval('Wasser läuft aus. Ablaufschlauch befestigen.', True, 'Handbuch', [])


def test_typo_and_colloquial_question_get_one_grounded_retry(monkeypatch):
    service, searches, prompts, providers, closed = backend(monkeypatch, [MISS, HIT])
    result = service.retrieve('Wasser schießt aus der Maxchine', 'hybrid', 'openai', 'test-key')
    assert result.grounded
    assert result.search_query == 'Wasser läuft aus'
    assert searches == ['Wasser schießt aus der Maxchine', 'Wasser läuft aus']
    assert len(prompts) == 1
    assert 'Wasser schießt aus der Maxchine' in prompts[0]
    assert providers == [('openai', 'test-key')]
    assert closed == [True]


def test_grounded_first_search_does_not_call_llm(monkeypatch):
    service, searches, prompts, _, _ = backend(monkeypatch, [HIT])
    assert service.retrieve('Wasser läuft aus', 'hybrid').grounded
    assert len(searches) == 1
    assert not prompts


@pytest.mark.parametrize('question', ['E:999', 'Fehler E:180', 'E:18 und Wasser schießt heraus'])
def test_error_codes_are_never_reinterpreted(monkeypatch, question):
    service, searches, prompts, _, _ = backend(monkeypatch, [MISS])
    assert not service.retrieve(question, 'hybrid').grounded
    assert searches == [question]
    assert not prompts


@pytest.mark.parametrize('rewrite', [
    '{"query":null}', '{}', 'not JSON', '[]', '{"query":42}',
    '{"query":""}', '{"query":"E:23 Wasser läuft aus"}',
    '{"query":"' + 'x'*401 + '"}', '{"query":"Wasser schießt aus der Maxchine"}',
    RuntimeError('private-provider-error'),
])
def test_invalid_rewrite_keeps_abstention_and_closes_cloud_client(monkeypatch, rewrite):
    service, searches, _, _, closed = backend(monkeypatch, [MISS], rewrite)
    result = service.retrieve('Wasser schießt aus der Maxchine', 'hybrid', 'openai', 'test-key')
    assert not result.grounded
    assert len(searches) == 1
    assert closed == [True]


def test_rewrite_does_not_bypass_grounding_or_loop(monkeypatch):
    service, searches, prompts, _, _ = backend(monkeypatch, [MISS])
    assert not service.retrieve('Wasser schießt aus der Maxchine', 'hybrid', 'local').grounded
    assert len(searches) == 2
    assert len(prompts) == 1


def test_unavailable_rewriter_keeps_normal_abstention(monkeypatch):
    service, *_ = backend(monkeypatch, [MISS])
    def unavailable(*a, **k):
        raise RuntimeError('missing-local-model')
    monkeypatch.setattr(service, 'llm', unavailable)
    assert not service.retrieve('Wasser schießt aus der Maxchine', 'hybrid').grounded


@pytest.mark.parametrize('endpoint', ['/api/ask', '/api/ask_stream'])
def test_answer_uses_original_question_and_reports_rewrite(monkeypatch, endpoint):
    service, *_ = backend(monkeypatch, [MISS, HIT])
    original = 'Wasser schießt aus der Maxchine'
    def answer(messages, stream=False, **kwargs):
        assert json.loads(messages[1]['content'])['frage'] == original
        raw = '<summary>Wasser läuft aus</summary><manual_steps>- Ablaufschlauch befestigen.</manual_steps>'
        if stream:
            return iter([NS(usage=None, choices=[NS(delta=NS(content=raw))])])
        return NS(choices=[NS(message=NS(content=raw))])
    monkeypatch.setattr(service, 'answer', answer)
    client = server.create_app(service).test_client()
    result = client.post(endpoint, json={'frage': original, 'provider':'local'})
    assert result.status_code == 200
    if endpoint.endswith('stream'):
        blocks = result.get_data(as_text=True).split('\n\n')
        event = next(block for block in blocks if block.startswith('event: result'))
        payload = json.loads(event.split('data: ', 1)[1])
    else:
        payload = result.json
    assert payload['search_query'] == 'Wasser läuft aus'


def test_local_model_json_code_fence_is_accepted(monkeypatch):
    service, searches, *_ = backend(monkeypatch, [MISS, HIT], '```json\n{"query":"Wasser läuft aus"}\n```')
    assert service.retrieve('Wasser schießt aus der Maxchine', 'hybrid', 'local').grounded
    assert searches[-1] == 'Wasser läuft aus'
