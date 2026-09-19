from types import SimpleNamespace as NS
import pytest
import server


class Backend:
    def __init__(self, grounded=True, fail=False):
        self.grounded, self.fail, self.calls = grounded, fail, 0
    def retrieve(self, question, mode, provider=None, api_key=None):
        if self.fail:
            raise RuntimeError('secret-internal-path')
        return 'E:23 Wasser in der Bodenwanne', self.grounded, 'Handbuch: Fehlercodes'
    def answer(self, messages, stream=False, provider=None, api_key=None):
        self.calls += 1
        assert messages[0]['role'] == 'system'
        raw = '<summary>E:23</summary><manual_intro>Im Handbuch:</manual_intro><manual_steps>- Wasserhahn schließen. Kundendienst rufen!</manual_steps>'
        if stream:
            return iter([NS(usage=None, choices=[NS(delta=NS(content=raw))])])
        return NS(choices=[NS(message=NS(content=raw))])


@pytest.mark.parametrize('body', [None, [], 'hi', {}, {'frage': 12}, {'frage': '   '}, {'frage': 'x'*2001}, {'frage':'test','mode':'wrong'}])
@pytest.mark.parametrize('endpoint', ['/api/ask', '/api/ask_stream'])
def test_bad_input(body, endpoint):
    client = server.create_app(Backend()).test_client()
    assert client.post(endpoint, json=body).status_code == 400


@pytest.mark.parametrize('path', ['/.env', '/server.py', '/.git/config', '/requirements.txt', '/profiles/openai/.env'])
def test_private_files_not_served(path):
    assert server.create_app(Backend()).test_client().get(path).status_code == 404


def test_static_and_health_without_models():
    client = server.create_app(Backend()).test_client()
    assert client.get('/').status_code == 200
    assert client.get('/api/health').json['status'] == 'ok'
    assert client.get('/mobile/').status_code == 200
    assert client.get('/mobile/guide.js').status_code == 200
    assert client.get('/mobile/../server.py').status_code == 404
    assert client.get('/mobile/.env').status_code == 404


def test_abstention_skips_llm():
    backend = Backend(grounded=False)
    client = server.create_app(backend).test_client()
    for endpoint in ('/api/ask', '/api/ask_stream'):
        r = client.post(endpoint, json={'frage':'Wer gewinnt die WM?'})
        assert r.status_code == 200
        assert 'Nicht im Handbuch' in r.get_data(as_text=True)
    assert backend.calls == 0


def test_retrieval_failure_is_handled_and_redacted():
    client = server.create_app(Backend(fail=True)).test_client()
    r = client.post('/api/ask', json={'frage':'E:23'})
    assert r.status_code == 503
    assert 'secret-internal-path' not in r.get_data(as_text=True)
    r = client.post('/api/ask_stream', json={'frage':'E:23'})
    assert 'event: error' in r.get_data(as_text=True)
    assert 'secret-internal-path' not in r.get_data(as_text=True)
    assert r.get_data(as_text=True).endswith('data: [DONE]\n\n')


def test_json_sse_equivalence():
    import json
    client = server.create_app(Backend()).test_client()
    expected = client.post('/api/ask',json={'frage':'E:23'}).json
    stream = client.post('/api/ask_stream',json={'frage':'E:23'}).get_data(as_text=True)
    result = next(b for b in stream.split('\n\n') if b.startswith('event: result'))
    actual = json.loads(result.split('data: ',1)[1])
    assert actual['results'] == expected['results']
    assert actual['tts_summary'] == expected['tts_summary']
    assert actual['usage'] is None


def test_malformed_output_is_not_manual_evidence():
    with pytest.raises(ValueError):
        server.parse_ai_response('Plain unverified model knowledge')


def test_repeated_step_tags_do_not_drop_answer_parts():
    raw = '<summary>E18</summary><manual_steps>- **Pumpe:** reinigen</manual_steps><manual_steps>- **Ablauf:** reinigen</manual_steps>'
    _, content, _ = server.parse_ai_response(raw)
    assert '**Pumpe:**' in content and '**Ablauf:**' in content
    assert content.count('- [ ]') == 2


def test_checkbox_conversion_preserves_bold_and_unbulleted_warnings():
    assert server.make_checkboxes('**Warnung:** abkühlen\n- **Strom:** Netzstecker ziehen') == '- [ ] **Warnung:** abkühlen\n- [ ] **Strom:** Netzstecker ziehen'


def test_context_budget_rejects_instead_of_silently_cutting():
    with pytest.raises(ValueError):
        server._messages('E:18','x'*20000)


def test_provider_is_routed_per_request(monkeypatch):
    seen = []
    class Recording(Backend):
        def retrieve(self, question, mode, provider=None, api_key=None):
            seen.append(("retrieve", provider))
            return server.Retrieval("E:23", True, "Handbuch", [{"id":"1", "text":"E:23"}])
        def answer(self, messages, stream=False, provider=None, api_key=None):
            seen.append(("answer", provider))
            return super().answer(messages, stream, provider)
    client = server.create_app(Recording()).test_client()
    configure_key(client)
    for provider in ("openai", "local", "openai"):
        result = client.post("/api/ask", json={"frage":"E:23", "provider":provider})
        assert result.json["provider"] == provider
        assert result.json["sources"][0]["id"] == "1"
    assert seen == [(phase, provider) for provider in ("openai", "local", "openai")
                    for phase in ("retrieve", "answer")]


def test_truncated_answer_is_rejected():
    class Truncated(Backend):
        def answer(self, messages, stream=False, provider=None, api_key=None):
            if stream:
                return iter([NS(usage=None, choices=[NS(finish_reason="length",
                               delta=NS(content="<summary>Halbe Antwort"))])])
            return NS(choices=[NS(finish_reason="length", message=NS(content="<summary>Halbe Antwort"))])
    client = server.create_app(Truncated()).test_client()
    assert client.post("/api/ask", json={"frage":"E:23"}).status_code == 503
    raw = client.post("/api/ask_stream", json={"frage":"E:23"}).get_data(as_text=True)
    assert "event: error" in raw and "event: result" not in raw


@pytest.mark.parametrize("provider,code", [("missing",400), ("openai",503)])
def test_unavailable_provider(monkeypatch, provider, code):
    client = server.create_app(Backend()).test_client()
    assert client.post("/api/ask", json={"frage":"E:18","provider":provider}).status_code == code


def configure_key(client, key="test-key-for-local-tests-only-123456"):
    csrf = client.get("/api/modes").json["csrf_token"]
    return client.post("/api/openai_key", json={"key":key}, headers={"X-CSRF-Token":csrf})


def test_key_is_private_to_browser_session_and_can_be_removed(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-be-used-from-environment")
    app = server.create_app(Backend())
    first, second = app.test_client(), app.test_client()
    assert first.get("/api/modes").json["openai_configured"] is False
    key = "test-private-key-should-never-be-returned"
    response = configure_key(first, key)
    assert response.json == {"configured":True}
    assert key not in response.get_data(as_text=True)
    modes = first.get("/api/modes")
    assert modes.json["openai_configured"] is True
    assert key not in modes.get_data(as_text=True)
    assert "no-store" in modes.headers["Cache-Control"]
    with first.session_transaction() as cookie:
        assert key not in str(dict(cookie))
        assert set(cookie) == {"sid", "csrf"}
    assert second.get("/api/modes").json["openai_configured"] is False
    assert second.post("/api/ask",json={"frage":"E:18","provider":"openai"}).status_code == 503
    assert configure_key(first, None).json == {"configured":False}
    assert first.get("/api/modes").json["openai_configured"] is False


def test_key_change_requires_csrf_and_local_same_origin():
    client = server.create_app(Backend()).test_client()
    csrf = client.get("/api/modes").json["csrf_token"]
    body = {"key":"test-key-for-this-test-only-123456"}
    assert client.post("/api/openai_key",json=body).status_code == 403
    assert client.post("/api/openai_key",json=body,headers={"X-CSRF-Token":csrf,
                       "Origin":"https://attacker.example"}).status_code == 403
    assert client.post("/api/openai_key",json=body,headers={"X-CSRF-Token":csrf},
                       environ_overrides={"REMOTE_ADDR":"192.0.2.10"}).status_code == 403
    assert client.get("/api/modes",headers={"Host":"attacker.example"}).status_code == 400
    assert client.get("/api/modes",headers={"Sec-Fetch-Site":"cross-site"}).status_code == 403


def test_key_never_appears_in_logs_or_api_errors(caplog):
    key = "test-private-key-from-provider-exception"
    class Failing(Backend):
        def answer(self, messages, stream=False, provider=None, api_key=None):
            raise RuntimeError(api_key)
    client = server.create_app(Failing()).test_client()
    configure_key(client, key)
    for endpoint in ["/api/ask", "/api/ask_stream"]:
        response = client.post(endpoint,json={"frage":"E:18","provider":"openai"})
        assert key not in response.get_data(as_text=True)
    assert key not in caplog.text


def test_key_reaches_only_selected_cloud_request():
    keys_seen = []
    class Recording(Backend):
        def answer(self, messages, stream=False, provider=None, api_key=None):
            keys_seen.append((provider,api_key))
            return super().answer(messages,stream,provider,api_key)
    client = server.create_app(Recording()).test_client()
    key = "test-private-key-for-routing-123456"
    configure_key(client,key)
    client.post("/api/ask",json={"frage":"E:18","provider":"openai"})
    client.post("/api/ask",json={"frage":"E:18","provider":"local"})
    assert keys_seen == [("openai",key),("local",None)]


@pytest.mark.parametrize("key", ["short", "x"*513, 123, "invalid key with spaces that is long", "\n"*25])
def test_invalid_key_rejected(key):
    client = server.create_app(Backend()).test_client()
    assert configure_key(client,key).status_code == 400
    assert client.get("/api/modes").json["openai_configured"] is False


def test_new_app_does_not_retain_previous_key():
    first = server.create_app(Backend()).test_client()
    configure_key(first)
    second = server.create_app(Backend()).test_client()
    assert second.get("/api/modes").json["openai_configured"] is False
