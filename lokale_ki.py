from llama_index.core import SimpleDirectoryReader, VectorStoreIndex, Settings
from llama_index.llms.openai import OpenAI
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.core import SimpleDirectoryReader, VectorStoreIndex, Settings, PromptTemplate
from llama_index.core.node_parser import MarkdownNodeParser

print("🧠 Starte KI-System...")

# 1. Ihr lokales Gemma-Modell in LM Studio anbinden
llm = OpenAI(
    api_base="http://192.168.178.183:1234/v1",
    api_key="lm-studio",  # LM Studio braucht einen Platzhalter-Key
    temperature=0.1,      # Sehr analytisch, wenig "Fantasie" (perfekt für Handbücher)
)

# 2. Lokales Embedding-Modell laden (läuft extrem schnell auf Apple Silicon)
# Wir nutzen ein kleines, starkes Modell, das auch Deutsch gut versteht
embed_model = HuggingFaceEmbedding(model_name="intfloat/multilingual-e5-small")

# 3. LlamaIndex mitteilen, dass wir ab jetzt zu 100% lokal arbeiten!
Settings.llm = llm
Settings.embed_model = embed_model

print("📚 Lese Siemens-Wissen (Markdown) ein...")
documents = SimpleDirectoryReader(input_files=["siemens_wissen.md"]).load_data()

# NEU: Wir zerschneiden das Dokument intelligent anhand der Markdown-Überschriften
print("✂️ Strukturiere das Dokument nach Kapiteln...")
parser = MarkdownNodeParser()
nodes = parser.get_nodes_from_documents(documents)

print("🔍 Erstelle vektorbasiertes Gedächtnis...")
index = VectorStoreIndex.from_documents(documents)

print("✅ System bereit!\n")

# 4. Die Suchmaschine starten
query_engine = index.as_query_engine(similarity_top_k=5)

# NEU: Wir zwingen Gemma in das exakte API-Format für Ihr Frontend
prompt_anweisung = """Du bist ein technischer Support-Mitarbeiter für Siemens Waschmaschinen.
Hier sind die exakten Informationen aus dem offiziellen Handbuch:
---------------------
{context_str}
---------------------
Regeln für deine Antwort:
1. Antworte ZWINGEND und AUSSCHLIESSLICH in einem gültigen JSON-Format.
2. Das JSON muss ein Array "results" enthalten.
3. Unterteile deine Antwort in zwei Blöcke: Erstens das Wissen strikt aus dem Handbuch ("manual"), zweitens allgemeine logische Tipps aus deinem Weltwissen ("internet").
4. Das JSON muss exakt dieses Schema haben:
{{
  "results": [
    {{
      "title": "Laut Siemens Handbuch",
      "content": "Deine detaillierten Stichpunkte basierend auf dem Handbuch-Text.",
      "sourceType": "manual",
      "reference": "Siemens Bedienungsanleitung"
    }},
    {{
      "title": "Zusätzliche Tipps",
      "content": "Weitere logische Ursachen (z.B. Flusensieb, Laugenpumpe), falls das Handbuch nicht reicht.",
      "sourceType": "internet",
      "reference": "Allgemeines Techniker-Wissen"
    }}
  ]
}}

Frage: {query_str}
Antwort:"""

# Den Prompt an die Suchmaschine übergeben
qa_template = PromptTemplate(prompt_anweisung)
query_engine.update_prompts({"response_synthesizer:text_qa_template": qa_template})

# 5. Unsere Testfrage
frage = "Wasser tritt unter der Maschine aus oder läuft aus. Was sind mögliche Ursachen und Lösungen?"
print(f"\nFrage: {frage}\n")
print("Gemma denkt nach...\n")

antwort = query_engine.query(frage)
print("🤖 Antwort von Gemma:")
print(antwort)