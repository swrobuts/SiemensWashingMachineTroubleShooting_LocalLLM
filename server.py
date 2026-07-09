import json
import os
import re
from flask import Flask, Response, request, jsonify
from flask_cors import CORS
from llama_index.core import Settings, PromptTemplate
from llama_index.core.llms import ChatMessage
from llama_index.llms.openai_like import OpenAILike

import rag_engine

app = Flask(__name__)
CORS(app)

# ==========================================
# VERSIONS-CHECK FÜR DAS TERMINAL
print("\n" + "=" * 50)
print("🚀 STARTE V14 — OpenAILike (explizites Modell) + Hybrid-RAG 🚀")
print("=" * 50 + "\n")
# ==========================================

# 1. Lokales Modell (LM Studio) anbinden.
#    OpenAILike statt OpenAI: erlaubt echte lokale Modellnamen (die OpenAI-Klasse
#    hat eine Whitelist und nutzte sonst zufällig 'gpt-3.5-turbo' als Platzhalter).
#    Modell/Endpoint per ENV überschreibbar.
# Default: schnelles Nicht-Reasoning-Instruct-Modell (Kiosk-tauglich, ~40 s statt
# ~250 s beim 27B-Reasoning-Modell). Per ENV überschreibbar.
LLM_MODEL = os.getenv("LOCAL_LLM_MODEL", "gemma-4-12b-it-mlx")
LLM_ENDPOINT = os.getenv("LOCAL_LLM_ENDPOINT", "http://127.0.0.1:1234/v1")
llm = OpenAILike(
    model=LLM_MODEL,
    api_base=LLM_ENDPOINT,
    api_key="lm-studio",
    is_chat_model=True,
    context_window=8192,
    temperature=0.0,
    timeout=1200.0,  # großzügig für langsame lokale Modelle
    max_tokens=2048,
)
Settings.llm = llm
print(f"🧠 LLM: {LLM_MODEL} @ {LLM_ENDPOINT}")

# 2. Index bauen oder aus dem Cache laden.
#    build_or_load_index() setzt Settings.embed_model (mit e5-Präfixen) und
#    persistiert den Index, sodass der Server künftig ohne Neu-Embedding startet.
print("📚 Initialisiere Siemens-Wissen (persistenter Vektorindex) …")
index = rag_engine.build_or_load_index()

# 3. PROMPT: Deutsch, XML-Zwang, Fokus auf maximale Tiefe.
prompt_anweisung = """System: Du bist ein hochqualifizierter technischer Support-Experte für Siemens Hausgeräte.
Deine Aufgabe ist es, das Handbuch extrem detailliert auszuwerten und dem Nutzer professionell, empathisch und in seiner Sprache zu antworten.

HANDBUCH-WISSEN (Kontext):
---------------------
{context_str}
---------------------

DEINE ANWEISUNGEN:
1. SPRACHE: Antworte ZWINGEND in der Sprache der Nutzerfrage. (Frage auf Deutsch = Antwort auf Deutsch).
2. MAXIMALE DETAILS: Fasse nicht oberflächlich zusammen! Extrahiere JEDES Detail, JEDES Bauteil und JEDEN Fehlercode exakt aus dem Text.
3. SPRACHSTIL: Formuliere fließende Einleitungen wie: "Wenn Wasser aus Ihrer Maschine läuft, empfiehlt die Bedienungsanleitung folgende Schritte:"
4. STRUKTUR: Nutze für die Handlungsschritte das Format "- **Bauteil/Thema:** Ausführliche Erklärung...".
5. XML-ZWANG: Du MUSST deine Antwort zwingend in diese XML-Tags verpacken:

<summary>1 kurzer, empathischer Satz zur Diagnose.</summary>
<manual_intro>1-2 freundliche Sätze als Einleitung zu den Handbuch-Schritten.</manual_intro>
<manual_steps>
- **Schritt 1:** Detailierte Erklärung...
- **Schritt 2:** Detailierte Erklärung...
</manual_steps>
<tips_intro>1 Satz Überleitung zu allgemeinen Tipps.</tips_intro>
<tips_steps>
- **Tipp 1:** Detailierte Erklärung...
</tips_steps>

Nutzerfrage: {query_str}
Antwort (NUR MIT XML-TAGS):"""

qa_template = PromptTemplate(prompt_anweisung)

# Retriever + Reranker einmalig; beide Endpunkte streamen/rufen das LLM direkt.
# (Der LlamaIndex-Query-Engine-Streaming-Pfad puffert und streamt NICHT
#  token-weise — deshalb umgehen wir ihn und rufen llm.stream_chat direkt.)
_stream_retriever = rag_engine.make_retriever(index)
_stream_reranker = rag_engine.get_reranker()

# Retrieval-Modus umschaltbar: "hybrid" (Vektor+Rerank) oder "pageindex"
# (vectorless, reasoning-based Baum-Navigation). Beide liefern (context, grounded, quelle).
RETRIEVAL_MODE = os.getenv("RETRIEVAL_MODE", "hybrid")
if RETRIEVAL_MODE == "pageindex":
    import pageindex_engine
    pageindex_engine.load_tree()
    _pi_complete = lambda p: llm.complete(p).text  # nutzt dasselbe LM-Studio-Modell
    print(f"🎯 Retrieval: PageIndex (vectorless) | Tree {pageindex_engine.TREE_PATH}")
else:
    print(
        f"🎯 Retrieval: hybrid top_k={rag_engine.RETRIEVE_K} → "
        + (f"Rerank({rag_engine.RERANK_MODEL}) → {rag_engine.FINAL_K}"
           if rag_engine.ENABLE_RERANK else "kein Rerank")
    )


def _retrieve_context(frage: str):
    """Einheitliche Retrieval-Schnittstelle → (context_str, grounded, quelle)."""
    if RETRIEVAL_MODE == "pageindex":
        ctx, nodes = pageindex_engine.retrieve_context(frage, complete=_pi_complete)
        return ctx, pageindex_engine.is_grounded(nodes), pageindex_engine.format_source_reference(nodes)
    nodes = _stream_retriever.retrieve(frage)
    if _stream_reranker:
        nodes = _stream_reranker.postprocess_nodes(nodes, query_str=frage)
    ctx = "\n\n".join(n.node.get_content() for n in nodes)
    return ctx, rag_engine.is_grounded(nodes), rag_engine.format_source_reference(nodes)


print("✅ System bereit!")
print("🌐 Der lokale Server lauscht jetzt auf http://localhost:3001")


# Hilfsfunktion für die XML-Tags (resistent gegen abgeschnittene Texte).
def extract_tag(text, tag):
    # Das (</{tag}>|$) am Ende rettet auch Text, wenn die KI mitten im Satz abbricht.
    match = re.search(f"<{tag}>(.*?)(</{tag}>|$)", text, re.DOTALL | re.IGNORECASE)
    return match.group(1).strip() if match else ""


def make_checkboxes(text):
    if not text:
        return ""
    lines = text.split("\n")
    out = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        line = re.sub(r"^[\-\*\•]\s*", "", line)
        line = re.sub(r"^\d+[\.\)]\s*", "", line)
        line = line.replace("- [ ]", "").replace("[ ]", "").strip()
        if line:
            out.append(f"- [ ] {line}")
    return "\n".join(out)


# Die absolut sichere Parse-Funktion.
def parse_ai_response(text):
    text = re.sub(r"```[a-zA-Z]*\n?", "", text).replace("```", "").strip()

    summary = extract_tag(text, "summary")
    man_intro = extract_tag(text, "manual_intro")
    man_steps = extract_tag(text, "manual_steps")
    tip_intro = extract_tag(text, "tips_intro")
    tip_steps = extract_tag(text, "tips_steps")

    if not summary and not man_intro and not man_steps:
        return "Hier sind die Informationen:", text, ""

    if not summary:
        summary = "Diagnose abgeschlossen:"

    manual_full = man_intro
    if man_steps:
        manual_full += "\n\n" + make_checkboxes(man_steps)

    tips_full = tip_intro
    if tip_steps:
        tips_full += "\n\n" + make_checkboxes(tip_steps)

    return summary.strip(), manual_full.strip(), tips_full.strip()


# API Endpunkt
@app.route("/api/ask", methods=["POST"])
def ask_ai():
    data = request.get_json()
    frage = data.get("frage", "")

    if not frage:
        return jsonify({"error": "Keine Frage gestellt"}), 400

    print(f"\nNeue Frage von der Webseite erhalten: '{frage}'")

    # Retrieval (Modus-abhängig) + Guardrail.
    context_str, grounded, quelle = _retrieve_context(frage)
    if not grounded:
        return jsonify({
            "tts_summary": rag_engine.NOT_IN_MANUAL,
            "results": [{
                "title": "❓ Nicht im Handbuch gefunden",
                "content": rag_engine.NOT_IN_MANUAL,
                "sourceType": "manual",
                "reference": "",
            }],
        })

    try:
        prompt = qa_template.format(context_str=context_str, query_str=frage)
        antwort_text = llm.chat([ChatMessage(role="user", content=prompt)]).message.content.strip()

        print(f"\n--- ROH-ANTWORT DER KI ---\n{antwort_text}\n--------------------------\n")

        tts_text, man_content, int_content = parse_ai_response(antwort_text)

        response_data = {
            "tts_summary": tts_text,
            "results": [
                {
                    "title": "📚 Handbuch / Manual",
                    "content": man_content,
                    "sourceType": "manual",
                    "reference": quelle,
                }
            ],
        }

        if int_content and len(int_content) > 5:
            response_data["results"].append({
                "title": "💡 Tipps / Tips",
                "content": int_content,
                "sourceType": "internet",
                "reference": "General Knowledge",
            })

        return jsonify(response_data)

    except Exception as e:
        error_msg = str(e)
        print(f"🚨 Fehler bei der Datenverarbeitung: {error_msg}")
        return jsonify({
            "tts_summary": "Systemfehler.",
            "results": [{
                "title": "Fehler",
                "content": f"- [ ] Ein technischer Fehler ist aufgetreten:\n{error_msg}",
                "sourceType": "internet",
                "reference": "System",
            }],
        })


def _sse(event, data):
    """Ein benanntes SSE-Event mit JSON-Payload (newline-sicher)."""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@app.route("/api/ask_stream", methods=["POST"])
def ask_ai_stream():
    """Wie /api/ask, aber streamt die Antwort Token für Token via SSE.

    Events: ``meta`` (Quelle) → viele ``token`` → ``result`` (strukturierte
    Karten nach XML-Parsing) → ``[DONE]``. So sieht der Nutzer sofort Text,
    statt minutenlang auf die fertige Antwort zu warten.
    """
    data = request.get_json()
    frage = data.get("frage", "")
    if not frage:
        return jsonify({"error": "Keine Frage gestellt"}), 400

    print(f"\n[stream] Neue Frage: '{frage}'")

    def generate():
        try:
            # 1. Retrieval (Modus-abhängig) → Quelle sofort senden.
            context_str, grounded, quelle = _retrieve_context(frage)

            # Guardrail: Frage nicht vom Handbuch gedeckt → nicht halluzinieren.
            if not grounded:
                yield _sse("meta", {"reference": ""})
                yield _sse("result", {
                    "tts_summary": rag_engine.NOT_IN_MANUAL,
                    "results": [{
                        "title": "❓ Nicht im Handbuch gefunden",
                        "content": rag_engine.NOT_IN_MANUAL,
                        "sourceType": "manual",
                        "reference": "",
                    }],
                })
                yield "data: [DONE]\n\n"
                return

            yield _sse("meta", {"reference": quelle})

            # 2. Das LLM DIREKT streamen (token-weise).
            prompt = qa_template.format(context_str=context_str, query_str=frage)

            parts = []
            for ch in llm.stream_chat([ChatMessage(role="user", content=prompt)]):
                delta = ch.delta or ""
                if delta:
                    parts.append(delta)
                    yield _sse("token", delta)

            raw = "".join(parts).strip()
            tts_text, man_content, int_content = parse_ai_response(raw)
            results = [{
                "title": "📚 Handbuch / Manual",
                "content": man_content,
                "sourceType": "manual",
                "reference": quelle,
            }]
            if int_content and len(int_content) > 5:
                results.append({
                    "title": "💡 Tipps / Tips",
                    "content": int_content,
                    "sourceType": "internet",
                    "reference": "General Knowledge",
                })
            yield _sse("result", {"tts_summary": tts_text, "results": results})
        except Exception as e:
            print(f"🚨 [stream] Fehler: {e}")
            yield _sse("error", {"message": str(e)})
        yield "data: [DONE]\n\n"

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=3001, threaded=True)
