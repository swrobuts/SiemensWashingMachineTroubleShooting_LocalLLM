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

# Beide Retrieval-Verfahren werden geladen; der Modus ist per Request umschaltbar
# ("hybrid" = Vektor+Rerank, "pageindex" = vectorless Baum-Navigation).
DEFAULT_MODE = os.getenv("RETRIEVAL_MODE", "hybrid")
# LiteLLM (lm_studio-Provider) für exakte Token-usage aus LM Studio.
try:
    import litellm as _litellm
    _litellm.drop_params = True
    os.environ.setdefault("LM_STUDIO_API_BASE", LLM_ENDPOINT)
    os.environ.setdefault("LM_STUDIO_API_KEY", "lm-studio")
    LITELLM_MODEL = "lm_studio/" + LLM_MODEL
except Exception:
    _litellm = None
    LITELLM_MODEL = None

_pi_available = False
try:
    import pageindex_engine
    if os.path.exists(pageindex_engine.TREE_PATH):
        pageindex_engine.load_tree()
        _pi_available = True
except Exception as _e:
    print(f"⚠️  PageIndex nicht verfügbar ({type(_e).__name__}: {_e}) — nur Hybrid-Modus")

print(f"🎯 Retrieval: hybrid (top_k={rag_engine.RETRIEVE_K}→Rerank→{rag_engine.FINAL_K})"
      f" | pageindex {'verfügbar' if _pi_available else 'NICHT verfügbar'} | Default: {DEFAULT_MODE}"
      f" | exakte usage: {'ja' if _litellm else 'nein (Schätzung)'}")


def _count_tokens(text: str) -> int:
    """Fallback-Schätzung, nur falls LiteLLM/usage nicht verfügbar."""
    if not text:
        return 0
    if _litellm is not None:
        try:
            return _litellm.token_counter(model="gpt-3.5-turbo", text=text)
        except Exception:
            pass
    return len(text) // 4


def _llm_complete_exact(prompt: str, usage_acc: dict) -> str:
    """Nicht-streamender LLM-Call via LiteLLM; summiert EXAKTE usage in usage_acc."""
    r = _litellm.completion(model=LITELLM_MODEL, messages=[{"role": "user", "content": prompt}], temperature=0)
    u = r.usage
    usage_acc["in"] += u.prompt_tokens
    usage_acc["out"] += u.completion_tokens
    return r.choices[0].message.content or ""


def _retrieve_context(frage: str, mode: str = None):
    """→ (context, grounded, quelle, retrieval_tokens) — Retrieval-Tokens EXAKT."""
    mode = mode or DEFAULT_MODE
    if mode == "pageindex" and _pi_available:
        nav = {"in": 0, "out": 0}
        if _litellm is not None:
            complete = lambda p: _llm_complete_exact(p, nav)  # noqa: E731
        else:
            complete = lambda p: llm.complete(p).text  # noqa: E731
        ctx, nodes = pageindex_engine.retrieve_context(frage, complete=complete)
        retr_tokens = (nav["in"] + nav["out"]) if _litellm is not None else pageindex_engine.nav_token_estimate(frage)
        return ctx, pageindex_engine.is_grounded(nodes), pageindex_engine.format_source_reference(nodes), retr_tokens
    nodes = _stream_retriever.retrieve(frage)
    if _stream_reranker:
        nodes = _stream_reranker.postprocess_nodes(nodes, query_str=frage)
    ctx = "\n\n".join(n.node.get_content() for n in nodes)
    return ctx, rag_engine.is_grounded(nodes), rag_engine.format_source_reference(nodes), 0  # hybrid: exakt 0


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

    mode = data.get("mode") or DEFAULT_MODE
    if mode == "pageindex" and not _pi_available:
        mode = "hybrid"
    print(f"\nNeue Frage ({mode}): '{frage}'")

    # Retrieval (Modus-abhängig) + Guardrail.
    context_str, grounded, quelle, _retr_tokens = _retrieve_context(frage, mode)
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
    mode = data.get("mode") or DEFAULT_MODE
    if mode == "pageindex" and not _pi_available:
        mode = "hybrid"
    if not frage:
        return jsonify({"error": "Keine Frage gestellt"}), 400

    print(f"\n[stream:{mode}] Neue Frage: '{frage}'")

    def generate():
        try:
            # 1. Retrieval (Modus-abhängig) → Quelle sofort senden.
            context_str, grounded, quelle, retr_tokens = _retrieve_context(frage, mode)

            # Guardrail: Frage nicht vom Handbuch gedeckt → nicht halluzinieren.
            if not grounded:
                yield _sse("meta", {"reference": "", "mode": mode})
                yield _sse("result", {
                    "tts_summary": rag_engine.NOT_IN_MANUAL,
                    "results": [{
                        "title": "❓ Nicht im Handbuch gefunden",
                        "content": rag_engine.NOT_IN_MANUAL,
                        "sourceType": "manual",
                        "reference": "",
                    }],
                    "usage": {"mode": mode, "retrieval": retr_tokens, "answer_in": 0,
                              "answer_out": 0, "total": retr_tokens},
                })
                yield "data: [DONE]\n\n"
                return

            yield _sse("meta", {"reference": quelle, "mode": mode})

            # 2. Antwort streamen — via LiteLLM mit EXAKTER usage aus LM Studio.
            prompt = qa_template.format(context_str=context_str, query_str=frage)
            parts = []
            answer_in = answer_out = 0
            if _litellm is not None:
                stream = _litellm.completion(
                    model=LITELLM_MODEL,
                    messages=[{"role": "user", "content": prompt}],
                    stream=True, stream_options={"include_usage": True},
                    temperature=0.0, max_tokens=2048,
                )
                for ch in stream:
                    u = getattr(ch, "usage", None)
                    if u:
                        answer_in, answer_out = u.prompt_tokens, u.completion_tokens
                    choices = ch.choices or []
                    if choices:
                        delta = getattr(choices[0].delta, "content", None) or ""
                        if delta:
                            parts.append(delta)
                            yield _sse("token", delta)
            else:
                for ch in llm.stream_chat([ChatMessage(role="user", content=prompt)]):
                    delta = ch.delta or ""
                    if delta:
                        parts.append(delta)
                        yield _sse("token", delta)

            raw = "".join(parts).strip()
            if not answer_out:  # Fallback, falls keine usage geliefert wurde
                answer_in = answer_in or _count_tokens(prompt)
                answer_out = _count_tokens(raw)
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
            yield _sse("result", {
                "tts_summary": tts_text, "results": results,
                "usage": {"mode": mode, "retrieval": retr_tokens, "answer_in": answer_in,
                          "answer_out": answer_out, "total": retr_tokens + answer_in + answer_out},
            })
        except Exception as e:
            print(f"🚨 [stream] Fehler: {e}")
            yield _sse("error", {"message": str(e)})
        yield "data: [DONE]\n\n"

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# Gemessene Vergleichsdaten (Zielmaschine, gemma-4-12b, 10 Fragen bzw. Beispiel E:18)
# für die Analyse-Registerkarte.
_COMPARISON = {
    "hybrid": {
        "label": "Hybrid + Reranking",
        "hit1": 100, "mrr": 1.00, "recall": 96, "latency_s": 2,
        "tokens": {"retrieval": 0, "answer": 1262, "total": 1262},
    },
    "pageindex": {
        "label": "PageIndex (vectorless)",
        "hit1": 70, "mrr": 0.82, "recall": 88, "latency_s": 104,
        "tokens": {"retrieval": 12261, "answer": 2822, "total": 15083},
    },
}


@app.route("/api/modes", methods=["GET"])
def api_modes():
    return jsonify({
        "default": DEFAULT_MODE,
        "pageindex_available": _pi_available,
        "comparison": _COMPARISON,
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=3001, threaded=True)
