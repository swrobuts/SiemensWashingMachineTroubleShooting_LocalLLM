"""Verify provider isolation and the actual OpenAI-compatible HTTP contract."""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
import llm_client


def test_local_http_contract_and_cloud_isolation(monkeypatch):
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass
        def do_GET(self):
            self.send({"object": "list", "data": [{"id": "loaded-test-model", "object": "model"}]})
        def do_POST(self):
            data = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests.append(data)
            self.send({"id": "test", "object": "chat.completion", "created": 0,
                       "model": data["model"], "choices": [{"index": 0,
                       "message": {"role": "assistant", "content": "Testantwort"},
                       "finish_reason": "stop"}]})
        def send(self, data):
            raw = json.dumps(data).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = Thread(target=httpd.serve_forever, daemon=True)
    worker.start()
    monkeypatch.setenv("LOCAL_LLM_ENDPOINT", f"http://127.0.0.1:{httpd.server_port}/v1")
    monkeypatch.setenv("LOCAL_LLM_MODEL", "")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-never-sent")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-4.1-mini")
    try:
        local = llm_client.make_llm("local")
        cloud = llm_client.make_llm("openai", api_key="explicit-test-key")
        assert str(cloud.client.base_url) == "https://api.openai.com/v1/"
        assert local.complete("E:18") == "Testantwort"
        assert requests[0]["model"] == "loaded-test-model"
        assert requests[0]["messages"][0]["content"] == "E:18"
        assert str(local.client.base_url).startswith("http://127.0.0.1:")
        local.client.close()
        cloud.client.close()
    finally:
        httpd.shutdown()
        httpd.server_close()
        worker.join()


def test_cloud_requires_explicit_key_even_if_environment_has_one(monkeypatch):
    import pytest
    monkeypatch.setenv("OPENAI_API_KEY", "environment-key-must-be-ignored")
    with pytest.raises(ValueError):
        llm_client.make_llm("openai")
