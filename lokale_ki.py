"""CLI: Das Siemens-Handbuch lokal befragen — gleiche RAG-Pipeline wie server.py.

Nutzt den geteilten rag_engine (Hybrid-Retriever + Reranker + Quellenzitat) und
streamt die Antwort direkt ins Terminal.

Beispiele:
    python3 lokale_ki.py "Was bedeutet Fehler E:23?"
    python3 lokale_ki.py            # interaktiver Modus

Voraussetzungen: LM Studio läuft mit einem geladenen Modell (Port 1234).
Konfiguration per ENV: LOCAL_LLM_MODEL, LOCAL_LLM_ENDPOINT, EMBED_MODEL, RERANK_MODEL.
"""
from __future__ import annotations

import os
import sys

from llama_index.core import Settings
from llama_index.core.llms import ChatMessage
from llama_index.llms.openai_like import OpenAILike

import rag_engine

MODEL = os.getenv("LOCAL_LLM_MODEL", "gemma-4-12b-it-mlx")
ENDPOINT = os.getenv("LOCAL_LLM_ENDPOINT", "http://127.0.0.1:1234/v1")

PROMPT = """Du bist technischer Support für Siemens Waschmaschinen. Nutze NUR das
Handbuch-Wissen unten. Antworte auf Deutsch, präzise, in Stichpunkten, und nenne
konkrete Bauteile und Schritte. Fehlt die Information im Kontext, sage das ehrlich.

Handbuch-Kontext:
---------------------
{context}
---------------------
Frage: {frage}
Antwort:"""


def main() -> None:
    Settings.llm = OpenAILike(
        model=MODEL, api_base=ENDPOINT, api_key="lm-studio",
        is_chat_model=True, context_window=8192,
        temperature=0.0, max_tokens=800, timeout=600,
    )
    print(f"🧠 {MODEL} @ {ENDPOINT}")
    index = rag_engine.build_or_load_index()
    retriever = rag_engine.make_retriever(index)
    reranker = rag_engine.get_reranker()

    def antworte(frage: str) -> None:
        nodes = retriever.retrieve(frage)
        if reranker:
            nodes = reranker.postprocess_nodes(nodes, query_str=frage)
        # Guardrail: nicht vom Handbuch gedeckt → nicht halluzinieren.
        if not rag_engine.is_grounded(nodes):
            print("\n" + rag_engine.NOT_IN_MANUAL + "\n")
            return
        ctx = "\n\n".join(n.node.get_content() for n in nodes)
        print(f"\n📚 Quelle: {rag_engine.format_source_reference(nodes)}\n")
        prompt = PROMPT.format(context=ctx, frage=frage)
        for ch in Settings.llm.stream_chat([ChatMessage(role="user", content=prompt)]):
            sys.stdout.write(ch.delta or "")
            sys.stdout.flush()
        print("\n")

    args = [a for a in sys.argv[1:] if a.strip()]
    if args:
        antworte(" ".join(args))
        return

    print("Interaktiver Modus — leere Eingabe beendet.")
    while True:
        try:
            frage = input("\n❓ ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not frage:
            break
        antworte(frage)


if __name__ == "__main__":
    main()
