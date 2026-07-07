import json
import re
from flask import Flask, request, jsonify
from flask_cors import CORS
from llama_index.core import SimpleDirectoryReader, VectorStoreIndex, Settings, PromptTemplate
from llama_index.core.node_parser import MarkdownNodeParser
from llama_index.llms.openai import OpenAI
from llama_index.embeddings.huggingface import HuggingFaceEmbedding

app = Flask(__name__)
CORS(app)

# ==========================================
# VERSIONS-CHECK FÜR DAS TERMINAL
print("\n" + "=" * 50)
print("🚀 STARTE NEUE VERSION (V12 - MASSIVER TIMEOUT FIX FÜR QWEN) 🚀")
print("=" * 50 + "\n")
# ==========================================

# 1. Lokales Modell (LM Studio) anbinden
llm = OpenAI(
    api_base="http://127.0.0.1:1234/v1",
    api_key="lm-studio",
    temperature=0.0,
    # HIER IST DER FIX FÜR QWEN: Massive Zeiterweiterung!
    # Wir geben dem Modell jetzt 20 Minuten (1200 Sekunden) Zeit zum Tippen.
    timeout=1200.0,
    request_timeout=1200.0,
    # Wir erlauben eine sehr lange Antwort
    max_tokens=2048
)

# 2. Embedding-Modell
embed_model = HuggingFaceEmbedding(model_name="intfloat/multilingual-e5-small")

Settings.llm = llm
Settings.embed_model = embed_model

# 3. Dokument laden
print("📚 Lese Siemens-Wissen (Markdown) ein...")
documents = SimpleDirectoryReader(input_files=["siemens_wissen.md"]).load_data()
parser = MarkdownNodeParser()
nodes = parser.get_nodes_from_documents(documents)

print("🔍 Erstelle vektorbasiertes Gedächtnis...")
index = VectorStoreIndex(nodes)
query_engine = index.as_query_engine(similarity_top_k=6)

# 5. PROMPT: Komplett auf Deutsch, API-Sprachstil und Fokus auf maximale Tiefe
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
query_engine.update_prompts({"response_synthesizer:text_qa_template": qa_template})

print("✅ System bereit!")
print("🌐 Der lokale Server lauscht jetzt auf http://localhost:3001")


# Hilfsfunktion für die XML-Tags (Jetzt resistent gegen abgeschnittene Texte!)
def extract_tag(text, tag):
    # Das (</{tag}>|$) am Ende sorgt dafür, dass auch Text gerettet wird,
    # wenn die KI mitten im Satz abbricht.
    match = re.search(f"<{tag}>(.*?)(</{tag}>|$)", text, re.DOTALL | re.IGNORECASE)
    return match.group(1).strip() if match else ""


def make_checkboxes(text):
    if not text: return ""
    lines = text.split('\n')
    out = []
    for line in lines:
        line = line.strip()
        if not line: continue
        line = re.sub(r'^[\-\*\•]\s*', '', line)
        line = re.sub(r'^\d+[\.\)]\s*', '', line)
        line = line.replace('- [ ]', '').replace('[ ]', '').strip()
        if line:
            out.append(f"- [ ] {line}")
    return '\n'.join(out)


# Die absolut sichere Parse-Funktion
def parse_ai_response(text):
    text = re.sub(r'```[a-zA-Z]*\n?', '', text).replace('```', '').strip()

    summary = extract_tag(text, 'summary')
    man_intro = extract_tag(text, 'manual_intro')
    man_steps = extract_tag(text, 'manual_steps')
    tip_intro = extract_tag(text, 'tips_intro')
    tip_steps = extract_tag(text, 'tips_steps')

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


# 6. API Endpunkt
@app.route('/api/ask', methods=['POST'])
def ask_ai():
    data = request.get_json()
    frage = data.get("frage", "")

    if not frage:
        return jsonify({"error": "Keine Frage gestellt"}), 400

    print(f"\nNeue Frage von der Webseite erhalten: '{frage}'")

    try:
        antwort = query_engine.query(frage)
        antwort_text = str(antwort).strip()

        print(f"\n--- ROH-ANTWORT DER KI ---\n{antwort_text}\n--------------------------\n")

        tts_text, man_content, int_content = parse_ai_response(antwort_text)

        response_data = {
            "tts_summary": tts_text,
            "results": [
                {
                    "title": "📚 Handbuch / Manual",
                    "content": man_content,
                    "sourceType": "manual",
                    "reference": "Siemens Manual"
                }
            ]
        }

        if int_content and len(int_content) > 5:
            response_data["results"].append({
                "title": "💡 Tipps / Tips",
                "content": int_content,
                "sourceType": "internet",
                "reference": "General Knowledge"
            })

        return jsonify(response_data)

    except Exception as e:
        error_msg = str(e)
        print(f"🚨 Fehler bei der Datenverarbeitung: {error_msg}")
        return jsonify({
            "tts_summary": "Systemfehler.",
            "results": [{"title": "Fehler", "content": f"- [ ] Ein technischer Fehler ist aufgetreten:\n{error_msg}",
                         "sourceType": "internet", "reference": "System"}]
        })


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=3001)