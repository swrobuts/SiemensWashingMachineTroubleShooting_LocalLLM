# Technische Dokumentation — Lokaler Siemens-Troubleshooting-Assistent

Ein vollständig lokaler RAG-Assistent (Retrieval-Augmented Generation), der Fragen
zu einer Siemens-Waschmaschine aus dem offiziellen Handbuch beantwortet — DSGVO-
konform (keine Cloud), mit Quellenangabe und Halluzinationsschutz.

---

## 1. Architekturüberblick

Die Verarbeitung zerfällt in zwei Phasen: die **Offline-Aufbereitung** (PDF →
durchsuchbarer Vektorindex, einmalig) und die **Online-Abfrage** (Frage → Antwort,
pro Nutzeranfrage).

```
OFFLINE (einmalig)                         ONLINE (pro Frage)
──────────────────                         ──────────────────
siemens-handbuch.pdf                       Nutzerfrage
   │ ① Docling                                 │ ⑥ Hybrid-Retrieval
   ▼                                           │    (Vektor + Fehlercode-Lookup)
siemens_wissen.md                              ▼
   │ ② Chunking (Markdown + Tabellen)      Kandidaten-Chunks
   ▼                                           │ ⑦ Cross-Encoder-Reranking
Text-Chunks (Nodes)                            ▼
   │ ③ lokale Embeddings (e5)              Top-5 relevante Chunks
   ▼                                           │ ⑧ Guardrail (Score-Schwelle)
Vektoren                                       ▼
   │ ④ Vektorindex                         Kontext + Prompt
   ▼                                           │ ⑨ lokales LLM (LM Studio), Streaming
storage/ (persistenter Index) ⑤               ▼
                                           Antwort (+ Quelle, live gestreamt)
```

| Schritt | Komponente | Datei |
|---------|-----------|-------|
| ① Extraktion | Docling | `parser.py` |
| ②–⑧ RAG-Kern | Chunking, Embedding, Index, Retrieval, Rerank, Guardrail | `rag_engine.py` |
| ⑨ Bedienung | Web-API + Streaming / Terminal-CLI | `server.py`, `lokale_ki.py`, `index.html` |

---

## 2. Dokumentenaufbereitung (Schwerpunkt)

Dies ist der qualitätsentscheidende Teil: Ein RAG-System kann nur so gut antworten,
wie der abgerufene Kontext gut ist. Jeder der folgenden Schritte wurde per
Retrieval-Eval (`eval/run_eval.py`) messbar begründet.

### Schritt 1 — PDF-Extraktion mit Docling (`parser.py`)

Das Handbuch ist ein visuell gesetztes PDF (mehrspaltig, mit Tabellen, Symbolen und
Warnhinweisen). Naive Text-Extraktion (z. B. `pdfplumber`) zerreißt Lesereihenfolge
und Tabellen. Stattdessen kommt **Docling** (IBM) zum Einsatz:

```python
from docling.document_converter import DocumentConverter
converter = DocumentConverter()
result = converter.convert("siemens-handbuch.pdf")
markdown = result.document.export_to_markdown()
```

Docling analysiert das Layout KI-gestützt (Lesereihenfolge, Tabellenstruktur, OCR)
und liefert **strukturiertes Markdown**: Überschriften als `##`, Tabellen als
Markdown-Pipe-Tabellen. Das Ergebnis (`siemens_wissen.md`) ist die Wissensbasis.

> **Warum Markdown als Zwischenformat?** Es ist verlustarm strukturiert, für
> Menschen prüfbar (man kann die Extraktion mit dem PDF vergleichen) und lässt sich
> strukturbewusst chunken (an Überschriften/Tabellen).

### Schritt 2 — Struktur der Wissensbasis verstehen

`siemens_wissen.md` umfasst ~1.900 Zeilen mit **187 `##`-Abschnitten** und **~190
Tabellenzeilen**. Zwei Besonderheiten prägen das Chunking:

1. **Die Kronjuwelen sind Tabellen.** Fehlercodes und Störungen stehen in zwei
   großen Tabellen („Hinweise im Anzeigefeld", „Störungen, was tun?"). Beispiel:

   | Anzeige | Ursache/Abhilfe |
   |---------|-----------------|
   | E:18 | Laugenpumpe verstopft. Laugenpumpe reinigen. ~ Seite 30. Ablaufschlauch/Abflussrohr verstopft. |
   | E:23 | Wasser in der Bodenwanne, Geräte-Undichtigkeit. Wasserhahn schließen. Kundendienst rufen! ~ Seite 36 |

2. **OCR-Artefakte.** Manche Docling-Überschriften sind verrauscht
   (z. B. `## S i h c r e n w s t Elektrische Sicherheit`). Sie stören das Retrieval
   nur geringfügig, weil die eigentlichen Antworten im Tabellen-/Fließtext stehen.

### Schritt 3 — Chunking: Markdown-Struktur + zeilenweise Tabellen

Zwei Stufen (`rag_engine._explode_markdown_tables`, `build_or_load_index`):

**a) Struktur-Chunking.** `MarkdownNodeParser` (LlamaIndex) schneidet das Dokument an
den `##`-Überschriften. Jeder Abschnitt wird ein „Node" mit Überschriften-Kontext.

**b) Tabellen-Explosion (der entscheidende Schritt).** Problem: Die Fehlercode-Tabelle
landet als **ein einziger ~6.400-Zeichen-Node**. So ein großer, heterogener Block
embeddet als semantischer „Brei" — eine konkrete Frage wie „Fehler E:18" findet ihn
**nicht** (empirisch: nicht unter den Top-60 Vektortreffern). Lösung: große
tabellenlastige Nodes werden **pro Zeile** aufgeteilt, jede Zeile mit Überschrift +
Spaltenlabels als lesbarer Fließtext gerendert (statt gepaddter Rohzeile, deren
Ausrichtungs-Whitespace das Embedding dominieren würde):

```
Vorher (1 Node, 6.400 Zeichen):
  ## Hinweise im Anzeigefeld | Anzeige | Ursache/Abhilfe | ... E:18 ... E:23 ... (alle Zeilen)

Nachher (viele kleine Nodes):
  ## Hinweise im Anzeigefeld
  Anzeige: E:18; Ursache/Abhilfe: Laugenpumpe verstopft. Laugenpumpe reinigen. ~ Seite 30 ...
```

Ergebnis: aus 188 werden **352 Nodes**; jeder Fehlercode ist ein eigener,
auffindbarer Abschnitt.

### Schritt 4 — Lokale Embeddings mit korrekten Präfixen

Jeder Node wird in einen Vektor überführt — **lokal** (kein Cloud-Abfluss) mit
`intfloat/multilingual-e5-small` über `HuggingFaceEmbedding`.

**Kritischer Punkt:** e5-Modelle sind *asymmetrisch* trainiert und verlangen Präfixe
— Fragen als `query: …`, Dokumentstücke als `passage: …`. Ohne diese Präfixe sinkt
die Trefferqualität spürbar (das war der größte stille Bug der Ausgangsversion):

```python
HuggingFaceEmbedding(
    model_name="intfloat/multilingual-e5-small",
    query_instruction="query: ",
    text_instruction="passage: ",
)
```

### Schritt 5 — Vektorindex + Persistenz mit Invalidierung

Die Vektoren wandern in einen `VectorStoreIndex` (LlamaIndex, In-Memory-HNSW) und
werden nach `storage/` persistiert — sonst würde jeder Serverstart alles neu
embedden. Um einen *veralteten* Index nie fälschlich zu laden, wird ein
**Cache-Schlüssel** aus Quelldatei-Inhalt + Embedding-Modell + Parser-Version
gebildet (`rag_engine.compute_cache_key`). Ändert sich eines davon, wird automatisch
neu gebaut. So kann z. B. ein Wechsel des Embedding-Modells nie einen inkonsistenten
Index verwenden.

---

## 3. Retrieval-Pipeline (Online)

### Schritt 6 — Hybrides Retrieval (Vektor + Fehlercode-Lookup)

`rag_engine.make_retriever` kombiniert zwei Signale:

- **Vektorsuche** (Overfetch, `RETRIEVE_K=12`) für semantische Ähnlichkeit.
- **Exakter Fehlercode-Lookup**: Dense-Embeddings sind bei seltenen Tokens wie
  „E:18" prinzipiell schwach. Enthält die Frage einen Code (`extract_error_codes`
  erkennt `E:18`, `E18`, „Fehler 18"), wird der Chunk mit genau diesem Code
  **garantiert** ins Kandidatenset gelegt, damit der Reranker ihn hochziehen kann.

### Schritt 7 — Cross-Encoder-Reranking

Die ~12 Kandidaten werden von `BAAI/bge-reranker-v2-m3` (multilingual) neu bewertet:
Der Reranker liest **Frage und Chunk gemeinsam** und ist dadurch weit präziser als
reine Vektorähnlichkeit. Er reduziert auf die relevantesten **`FINAL_K=5`** Chunks —
genau das, was das LLM als Kontext sieht.

### Schritt 8 — Guardrail gegen Halluzination

Der Reranker liefert Sigmoid-Scores in `[0,1]`. Kalibriert auf der Zielmaschine:
In-Scope-Fragen scoren **≥ 0.435**, fachfremde Fragen **≈ 0.000**. Liegt der beste
Score unter der Schwelle `GUARDRAIL_MIN_SCORE=0.15`, wird **ohne LLM-Aufruf** mit
„das steht nicht im Handbuch" geantwortet (`rag_engine.is_grounded`). Zweite Schicht:
Der Prompt weist das Modell an, bei fehlender Information ehrlich zu sein.

---

## 4. Antwortgenerierung

### Schritt 9 — Lokales LLM, strukturierte Ausgabe, Streaming

Die Top-5-Chunks bilden den Kontext eines Prompts, den ein **lokales Modell in
LM Studio** beantwortet (`OpenAILike`-Client, Default `gemma-4-12b-it-mlx`). Wichtig:
ein **Nicht-Reasoning-Instruct-Modell** — Reasoning-Modelle „denken" minutenlang.

- **Strukturierte Ausgabe:** Der Prompt erzwingt XML-Tags (`<summary>`,
  `<manual_steps>`, `<tips_steps>`), die `server.parse_ai_response` robust (mit
  Fallback bei Abbruch) in Karten und Checklisten übersetzt.
- **Quellenzitat:** `rag_engine.format_source_reference` leitet aus den genutzten
  Chunks „Handbuch: <Abschnitt> · Seite NN" ab (die `~ Seite NN`-Verweise des
  Handbuchs) — überprüfbar statt hart verdrahtet.
- **Streaming (SSE):** `/api/ask_stream` sendet zuerst die Quelle (~1 s), dann die
  Antwort Token für Token. Wichtig: Der LlamaIndex-Query-Engine-Streaming-Pfad
  puffert; deshalb wird das LLM **direkt** gestreamt (`llm.stream_chat`). Das
  Frontend zeigt eine Live-Vorschau und rendert am Ende die strukturierten Karten.

---

## 5. Konfiguration (ENV)

| Variable | Default | Zweck |
|----------|---------|-------|
| `LOCAL_LLM_MODEL` | `gemma-4-12b-it-mlx` | Modell in LM Studio |
| `LOCAL_LLM_ENDPOINT` | `http://127.0.0.1:1234/v1` | LM-Studio-Endpoint |
| `EMBED_MODEL` | `intfloat/multilingual-e5-small` | lokales Embedding (Index rebuildet bei Wechsel) |
| `RERANK_MODEL` | `BAAI/bge-reranker-v2-m3` | Cross-Encoder-Reranker |
| `ENABLE_RERANK` | `1` | `0` = Reranking aus |
| `RETRIEVE_K` / `FINAL_K` | `12` / `5` | Overfetch bzw. finale Chunks |
| `GUARDRAIL_MIN_SCORE` | `0.15` | Mindest-Reranker-Score |

---

## 6. Evaluation

`eval/run_eval.py` misst die **Retrieval-Qualität ohne LLM** (nur Embedding +
Reranker) an 10 realen Störungsfragen, deren erwartete Stichwörter aus den echten
Handbuch-Tabellen stammen. Metriken: Trefferquote, **hit@1** (oberster Chunk
relevant), **MRR**, **Recall**. Vorher/Nachher (auf Zielmaschine gemessen):

| Metrik | Original | Final |
|--------|----------|-------|
| hit@1 | 40 % | **100 %** |
| Recall | 33 % | **96 %** |
| MRR | 0.52 | **1.00** |
| Out-of-Scope abgefangen | 0/6 | **6/6** |

---

## 7. Betrieb

```bash
python3 parser.py        # ① PDF → siemens_wissen.md (nur bei neuem PDF)
python3 server.py        # Web-API :3001 → index.html öffnen
python3 lokale_ki.py "Fehler E:23?"   # Terminal-CLI
python3 eval/run_eval.py              # Retrieval messen (ohne LLM)
python3 -m pytest tests/ -q           # Unit-Tests
```

Die Dokumentenverarbeitungs-Pipeline (Schritte ①–⑧) ist zusätzlich als
eigenständiges Colab-Notebook aufbereitet:
`notebooks/document_processing_pipeline.ipynb`.
