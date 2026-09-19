"""One OpenAI-compatible client for the local model, CLI and PageIndex."""
from __future__ import annotations

import os
from pathlib import Path
from dotenv import load_dotenv, dotenv_values

load_dotenv(Path(__file__).resolve().parent / ".env")


def configuration(provider):
    directory = "openai" if provider == "openai" else "local"
    values = dotenv_values(Path(__file__).resolve().parent / "profiles" / directory / ".env")
    # Read profiles without mutating process-global settings between requests.
    return {**values, **os.environ}


class LocalLLM:
    def __init__(self):
        from openai import OpenAI
        conf = configuration("local")
        self.client = OpenAI(base_url=conf.get("LOCAL_LLM_ENDPOINT", "http://127.0.0.1:1234/v1"),
                             api_key=conf.get("LOCAL_LLM_API_KEY", "lm-studio"),
                             timeout=float(conf.get("LLM_TIMEOUT", "180")), max_retries=0)
        self.model = conf.get("LOCAL_LLM_MODEL", "")

    def model_id(self):
        if not self.model:
            models = [m.id for m in self.client.models.list().data if "embed" not in m.id.lower()]
            if len(models) != 1:
                raise RuntimeError("LOCAL_LLM_MODEL auf die genaue ID des geladenen Chatmodells setzen.")
            self.model = models[0]
        return self.model

    def complete(self, prompt):
        response = self.client.chat.completions.create(
            model=self.model_id(), messages=[{"role": "user", "content": prompt}],
            temperature=0, max_tokens=512)
        return response.choices[0].message.content or ""

    def answer(self, messages, stream=False):
        options = {"stream_options": {"include_usage": True}} if stream else {}
        return self.client.chat.completions.create(
            model=self.model_id(), messages=messages, temperature=0, stream=stream,
            max_tokens=int(os.getenv("ANSWER_MAX_TOKENS", "1024")), **options)


class OpenAILLM(LocalLLM):
    def __init__(self, api_key):
        if not api_key:
            raise ValueError("OpenAI-Schlüssel in der Oberfläche für diese Sitzung eingeben.")
        from openai import OpenAI
        conf = configuration("openai")
        self.client = OpenAI(api_key=api_key, base_url="https://api.openai.com/v1",
                             timeout=float(conf.get("LLM_TIMEOUT", "90")), max_retries=0)
        self.model = conf.get("OPENAI_MODEL", "gpt-4.1-mini")


def make_llm(provider=None, api_key=None):
    provider = provider or os.getenv("LLM_PROVIDER", "local")
    if provider == "openai":
        return OpenAILLM(api_key)
    if provider == "local":
        return LocalLLM()
    raise ValueError("LLM_PROVIDER muss local oder openai sein")
