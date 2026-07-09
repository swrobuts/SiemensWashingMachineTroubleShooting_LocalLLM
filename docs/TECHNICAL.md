# Technische Dokumentation — Lokaler Siemens-Troubleshooting-Assistent

Vollständig lokales RAG-System (Retrieval-Augmented Generation), das Fragen zu
einer Siemens-Waschmaschine aus dem offiziellen Handbuch beantwortet — DSGVO-
konform (kein Cloud-Aufruf), mit Quellenangabe, Halluzinationsschutz und **zwei
umschaltbaren Retrieval-Verfahren** (Hybrid-Vektor und PageIndex/vectorless).

Diese Doku ist die technische Quelle der Wahrheit. Für eine bebilderte Fassung
zum Weitergeben siehe `Technische_Dokumentation.docx`; die Offline-Pipeline ist
zusätzlich als Colab-Notebook aufbereitet (`notebooks/`).

---

## 1. Architektur & Komponenten

| Datei | Verantwortung |
|-------|---------------|
| `parser.py` | Docling-Extraktion: `siemens-handbuch.pdf` → `siemens_wissen.md` |
| `rag_engine.py` | Chunking, lokale Embeddings, persistenter Vektorindex, Hybrid-Retriever, Reranker, Guardrail, Quellenzitat |
| `pageindex/` (vendored) | PageIndex-Tree-Erzeugung (`md_to_tree`) + Utilities (VectifyAI, MIT) |
| `build_pageindex_tree.py` | Erzeugt `pageindex_tree.json` (offline) |
| `pageindex_engine.py` | PageIndex-Retrieval: LLM-Baum-Navigation (vectorless) |
| `server.py` | Flask-API (`/api/ask`, `/api/ask_stream`), Modus-Umschaltung, Prompt, XML-Parsing, SSE |
| `lokale_ki.py` | Terminal-CLI (streamt in die Konsole) |
| `index.html` | Single-File-Frontend (Live-Streaming, TTS, QR) |
| `eval/` | Retrieval-Evaluation (Hybrid ohne LLM; PageIndex mit LLM) |

Zwei Phasen: **Offline-Aufbereitung** (PDF → durchsuchbarer Index, einmalig) und
**Online-Abfrage** (Frage → Antwort, pro Anfrage).

```
OFFLINE                                  ONLINE (pro Frage)
siemens-handbuch.pdf                     Frage
  │ Docling                                │ Retrieval  ── hybrid ──► Vektor+Fehlercode-Lookup ► Reranking
  ▼                                        │            └ pageindex ► LLM-Baum-Navigation
siemens_wissen.md                          ▼
  │ Chunking (+ Tabellen-Explosion)      Guardrail (grounded?) ──nein──► „nicht im Handbuch"
  ▼                                        │ ja
Embeddings (e5) ► Vektorindex (storage/)   ▼
Tree-Index (pageindex_tree.json)         LLM (LM Studio) ► Antwort (Streaming, + Quelle)
```

---

## 2. Dokumentenaufbereitung (Offline)

### 2.1 Docling-Extraktion (`parser.py`)

Das Handbuch ist visuell gesetzt (mehrspaltig, Tabellen, Symbole). Docling
analysiert das Layout KI-gestützt und exportiert strukturiertes Markdown:

```python
from docling.document_converter import DocumentConverter
result = DocumentConverter().convert("siemens-handbuch.pdf")
open("siemens_wissen.md", "w").write(result.document.export_to_markdown())
```

Ergebnis `siemens_wissen.md`: ~1.928 Zeilen, ~12.200 Wörter, **187 `##`-Abschnitte**,
**~189 Tabellenzeilen**. Zwei Eigenheiten steuern das Chunking:
1. Fehlercodes/Störungen liegen in zwei großen Tabellen („Hinweise im
   Anzeigefeld", „Störungen, was tun?").
2. OCR-Artefakte in einzelnen Überschriften (z. B. `## S i h c r e n w s t
   Elektrische Sicherheit`) — unkritisch, da Antworten im Tabellen-/Fließtext stehen.

### 2.2 Chunking (`rag_engine._explode_markdown_tables`)

Zweistufig: `MarkdownNodeParser` schneidet an den `##`-Überschriften; anschließend
werden **große tabellenlastige Nodes zeilenweise aufgeteilt**. Ohne diesen Schritt
ist die Fehlercode-Tabelle ein ~6.400-Zeichen-Block, der als „semantischer Brei"
embeddet und für „Fehler E:18" **nicht** abgerufen wird (empirisch nachgewiesen:
nicht unter den Top-60 Vektortreffern).

```python
def _explode_markdown_tables(nodes, max_chars=1600):
    out = []
    for node in nodes:
        text = node.get_content()
        table_lines = [l for l in text.split("\n") if l.strip().startswith("|")]
        if len(text) <= max_chars or len(table_lines) < 3:
            out.append(node); continue          # kleine/normale Nodes unverändert
        heading = " ".join(l for l in text.split("\n") if l.strip().startswith("#"))
        labels  = _split_row(table_lines[0])    # Spaltenüberschriften
        for row in table_lines[2:]:             # [1] = |---|-Trennzeile
            cells = _split_row(row)
            pairs = "; ".join(f"{l}: {v}" for l, v in zip(labels, cells) if v)
            out.append(TextNode(text=f"{heading}\n{pairs}"))
    return out

def _split_row(line):   # Zellen bereinigen: Ausrichtungs-Whitespace kollabieren
    return [re.sub(r"\s+", " ", c).strip() for c in line.strip().strip("|").split("|")]
```

Effekt: **188 → 352 Nodes**. Jede Fehlercode-Zeile wird ein eigener, als lesbarer
Fließtext gerenderter Chunk (z. B. `Anzeige: E:18; Ursache/Abhilfe: Laugenpumpe
verstopft …`) — statt einer gepaddten Rohzeile, deren Whitespace das Embedding
dominieren würde. Die Konstante `PARSER_VERSION` (aktuell `md-v3`) fließt in den
Cache-Schlüssel ein: Ändert sich die Chunking-Logik, wird der Index neu gebaut.

### 2.3 Lokale Embeddings mit e5-Präfixen

e5-Modelle sind **asymmetrisch** trainiert und verlangen Präfixe — Fragen `query:`,
Textstücke `passage:`. Ohne diese sinkt die Trefferqualität deutlich (der größte
stille Bug der Ausgangsversion):

```python
HuggingFaceEmbedding(model_name="intfloat/multilingual-e5-small",
                     query_instruction="query: ", text_instruction="passage: ")
```

`_needs_e5_prefix()` setzt die Präfixe nur für e5-Modelle; bei Wechsel auf z. B.
`bge-m3` (kein Präfix nötig) entfallen sie automatisch. Das Modell ist per ENV
`EMBED_MODEL` tauschbar.

### 2.4 Persistenter Index mit Hash-Invalidierung

```python
def compute_cache_key(md_path, embed_model, parser_version=PARSER_VERSION):
    h = hashlib.sha256()
    h.update(Path(md_path).read_bytes()); h.update(embed_model.encode()); h.update(parser_version.encode())
    return h.hexdigest()
```

Der Index (`VectorStoreIndex`, In-Memory-HNSW, Cosinus) wird nach `storage/`
persistiert. Beim Start: stimmt der gespeicherte Cache-Schlüssel (Inhalt +
Embedding-Modell + Parser-Version) → laden; sonst neu bauen. So kann ein
inkonsistenter Index (falsches Modell, alte Chunking-Logik) nie geladen werden.

---

## 3. Retrieval — zwei Verfahren

### 3.A Hybrid (Vektor + Fehlercode-Lookup + Reranking) — `RETRIEVAL_MODE=hybrid`

Dense-Embeddings finden **seltene Tokens wie „E:18" schlecht**. Der Hybrid-Retriever
holt daher zusätzlich zur Vektorsuche (Overfetch `RETRIEVE_K=12`) den exakt
passenden Fehlercode-Chunk garantiert dazu:

```python
_CODE_RE = re.compile(r"(?:\bE[:\s]?|\bfehler(?:code)?\s+)(\d{1,3})\b", re.IGNORECASE)
def extract_error_codes(q):     # "E23"/"E:23"/"Fehler 23" → {"E:23","E23"}
    return {f"E:{m}" for m in nums} | {f"E{m}" for m in nums}

class _HybridRetriever(BaseRetriever):
    def _retrieve(self, qb):
        nodes = self._vr.retrieve(qb)                    # Vektor Top-12
        for code in extract_error_codes(qb.query_str):   # + exakte Code-Chunks
            nodes += [NodeWithScore(node=n, score=1.0)
                      for n in self._docs if code in n.get_content()]
        return nodes
```

Danach **Cross-Encoder-Reranking** mit `BAAI/bge-reranker-v2-m3` (multilingual):
Der Reranker liest Frage + Chunk gemeinsam und reduziert auf die relevantesten
`FINAL_K=5` — genau das, was das LLM sieht. Reranking ändert den Index nicht
(rein nachgelagert). Latenz: praktisch sofort, **kein LLM nötig**.

### 3.B PageIndex (vectorless, reasoning-based) — `RETRIEVAL_MODE=pageindex`

Umsetzung von **VectifyAI PageIndex**: kein Embedding, keine Vektor-Ähnlichkeit.
Stattdessen wird offline ein **hierarchischer Tree-Index** (Inhaltsverzeichnis mit
Zusammenfassungen) gebaut, und zur Laufzeit **navigiert ein LLM den Baum** und wählt
die relevanten Abschnitte — wie ein Mensch, der ein Inhaltsverzeichnis nutzt.

**Tree-Erzeugung** (offline, `build_pageindex_tree.py`, lokal via LM Studio):
```python
tree = await md_to_tree("siemens_wissen.md", if_add_node_summary="yes",
                        summary_token_threshold=200, if_add_node_text="yes",
                        model="lm_studio/gemma-4-12b-it-mlx")
```
Ergebnis `pageindex_tree.json`: 187 Knoten, jeder mit `node_id`, `title`,
`summary` (LLM-generiert), `text`, `line_num`. Dauer einmalig ~6 min (187
Summary-Calls, seriell über LM Studio).

**Retrieval** (`pageindex_engine.search`, originalgetreu nach dem PageIndex-„Vectorless
RAG"-Cookbook): dem LLM werden `node_id`+`title`+`summary` gezeigt, es liefert die
relevante `node_list`, deren Volltext den Kontext bildet:
```python
SEARCH_PROMPT = 'Finde die node_ids der Abschnitte, die die Antwort enthalten. '
                'Antworte als JSON: {"node_list": [...]}'
```
Anpassung für dieses Handbuch: Der Baum ist **flach** (187 gleichrangige `##`),
und gemmas Kontextfenster ist klein. Daher navigiert die Suche **batch-weise**
(`PAGEINDEX_BATCH=30` Abschnitte pro LLM-Call, Summaries auf 160 Zeichen gekürzt)
→ ~7 Calls/Frage. LiteLLM (`lm_studio/`-Provider) hält alles lokal.

Guardrail-Äquivalent: leere `node_list` → nicht gedeckt. Quelle: Titel + `~ Seite
NN` aus dem Knotentext.

### 3.C Vergleich (gemessen, 10 reale Störungsfragen, lokal gemma-4-12b)

| Metrik | Hybrid+Rerank | PageIndex (vectorless) |
|--------|---------------|------------------------|
| Trefferquote (≥1 Stichwort) | 100 % | 100 % |
| hit@1 (oberster Knoten korrekt) | **100 %** | 70 % |
| MRR | **1.00** | 0.82 |
| Ø Recall | **96 %** | 88 % |
| Latenz/Frage | **~sofort** (LLM-frei) | ~104 s (7 LLM-Calls) |

**Einordnung:** Beide finden die Fehlercodes zuverlässig. Auf diesem *kleinen,
flachen* Handbuch ist Hybrid schneller und rankt präziser. PageIndex ist der
**erklärbare, reasoning-basierte** Ansatz (die Auswahl ist nachvollziehbar) und
spielt seine Stärke bei **großen, tief hierarchischen** Dokumenten aus, wo die
Baum-Navigation gegenüber flachem Chunking gewinnt. Umschaltbar per
`RETRIEVAL_MODE`; ein größeres Kontextfenster erlaubt Single-Shot- statt
Batch-Navigation und senkt die PageIndex-Latenz.

---

## 4. Guardrail (Anti-Halluzination)

Der bge-Reranker liefert Sigmoid-Scores in `[0,1]`. Auf der Zielmaschine gemessen:

| | Score-Bereich (Top-1) |
|---|---|
| In-Scope (10 Fragen) | 0.435 – 0.987 (Median 0.95) |
| Out-of-Scope (6 Fragen) | exakt 0.000 |

Daraus die Schwelle **`GUARDRAIL_MIN_SCORE=0.15`** (großer Abstand zu beiden
Verteilungen). `is_grounded(nodes)` prüft den Top-Score; darunter antwortet das
System „nicht im Handbuch" **ohne LLM-Aufruf**. Im PageIndex-Modus: leere
`node_list` = nicht gedeckt. Zweite Schicht: Der Prompt weist das Modell an, bei
fehlender Information ehrlich zu sein (fängt Rand-Fälle ab, die knapp über der
Schwelle liegen). Gemessen: 6/6 fachfremde Fragen abgefangen, 0 Fehlalarme.

---

## 5. Antwortgenerierung

Das lokale Modell (`OpenAILike` → LM Studio, Default `gemma-4-12b-it-mlx`, ein
**Nicht-Reasoning-Modell**: ~40 s statt ~250 s beim 27B-Reasoning-Modell) erhält
Kontext + Frage. Der Prompt erzwingt XML-Tags; `parse_ai_response` übersetzt sie
in Karten/Checklisten und ist **abbruchresistent**:

```python
def extract_tag(text, tag):
    # (</tag>|$) rettet auch Text, wenn die KI mitten im Satz abbricht
    m = re.search(f"<{tag}>(.*?)(</{tag}>|$)", text, re.DOTALL | re.IGNORECASE)
    return m.group(1).strip() if m else ""
```

Bei völlig fehlenden Tags wird der Rohtext als Antwort genutzt (Fallback). Die
**Quellenangabe** (`format_source_reference`) leitet aus den genutzten Chunks
„Handbuch: <Abschnitt> · Seite NN" ab (regex `Seite\s+(\d+)` auf den `~ Seite
NN`-Verweisen des Handbuchs).

---

## 6. Streaming (SSE) & API

`/api/ask_stream` streamt das LLM **direkt** (`llm.stream_chat`), weil der
LlamaIndex-Query-Engine-Streaming-Pfad puffert und nicht token-weise liefert.
Event-Protokoll:

```
event: meta    data: {"reference": "Handbuch: … · Seite 30/31"}   (nach Retrieval, ~1 s im Hybrid-Modus)
event: token   data: "<summary>Es tut mir …"                       (viele; Live-Vorschau)
event: result  data: {"tts_summary": "...", "results": [ ... ]}    (strukturierte Karten nach XML-Parse)
data: [DONE]
```

Das Frontend liest den Stream via `fetch`+`ReadableStream`, zeigt die Quelle
sofort, füllt eine Live-Vorschau (XML-Tags entfernt) und rendert am Ende die
Karten. Gemessene Latenzen (Hybrid, gemma-12B): Quelle @ 1,3 s, 1. Token @ 7,2 s,
440 Token bis ~42 s. `/api/ask` liefert dieselbe Antwort blockierend als JSON.

**Endpunkte:** `POST /api/ask` und `POST /api/ask_stream` (Body `{"frage": "..."}`),
`POST /api/tts` (falls konfiguriert). Beide Antwort-Endpunkte durchlaufen
`_retrieve_context(frage) → (context, grounded, quelle)` — die einzige Stelle, an
der der Retrieval-Modus greift.

---

## 7. Konfiguration (ENV)

| Variable | Default | Zweck |
|----------|---------|-------|
| `RETRIEVAL_MODE` | `hybrid` | `hybrid` oder `pageindex` |
| `LOCAL_LLM_MODEL` | `gemma-4-12b-it-mlx` | Antwort-Modell in LM Studio |
| `LOCAL_LLM_ENDPOINT` | `http://127.0.0.1:1234/v1` | LM-Studio-Endpoint |
| `EMBED_MODEL` | `intfloat/multilingual-e5-small` | lokales Embedding (Index rebuildet bei Wechsel) |
| `RERANK_MODEL` | `BAAI/bge-reranker-v2-m3` | Cross-Encoder-Reranker |
| `ENABLE_RERANK` | `1` | `0` = Reranking aus |
| `RETRIEVE_K` / `FINAL_K` | `12` / `5` | Overfetch bzw. finale Chunks (Hybrid) |
| `GUARDRAIL_MIN_SCORE` | `0.15` | Mindest-Reranker-Score |
| `PAGEINDEX_MODEL` | `lm_studio/gemma-4-12b-it-mlx` | LiteLLM-Modell für Tree + Navigation |
| `PAGEINDEX_BATCH` | `30` | Abschnitte pro Navigations-Call |
| `PAGEINDEX_MAX_NODES` | `5` | max. gewählte Knoten |

---

## 8. Evaluation

`eval/run_eval.py` (Hybrid, **ohne LLM**) und `eval/run_eval_pageindex.py`
(PageIndex, mit LLM) messen dieselben Metriken an 10 realen Störungsfragen aus
`eval/questions.json`, deren erwartete Stichwörter aus den echten Handbuch-Tabellen
stammen.

- **Recall** = |gefundene Stichwörter| / |erwartete Stichwörter| im Kontext.
- **hit@1** = Anteil Fragen, deren *oberster* Knoten ≥1 Stichwort enthält.
- **MRR** = Mittelwert von 1/Rang des ersten relevanten Knotens.

Vorher/Nachher (Hybrid, gemessen): hit@1 **40 % → 100 %**, Recall **33 % → 96 %**,
MRR **0.52 → 1.00**, Out-of-Scope abgefangen **0/6 → 6/6**. Die Zwischenschritte
(e5-Fix, Reranking, Tabellen-Chunking, Fehlercode-Lookup) sind einzeln per
`--no-rerank` / `EMBED_MODEL=…` reproduzierbar.

---

## 9. Betrieb & Reproduzierbarkeit

```bash
pip install -r requirements.txt         # inkl. litellm, sentence-transformers, docling
python3 parser.py                       # (nur bei neuem PDF) → siemens_wissen.md
python3 build_pageindex_tree.py         # (nur für PageIndex-Modus) → pageindex_tree.json

python3 server.py                       # Hybrid-Modus, http://localhost:3001 → index.html öffnen
RETRIEVAL_MODE=pageindex python3 server.py     # PageIndex-Modus
python3 lokale_ki.py "Fehler E:23?"     # Terminal-CLI

python3 eval/run_eval.py                # Hybrid-Eval (ohne LLM)
python3 eval/run_eval_pageindex.py      # PageIndex-Eval (mit LLM)
python3 -m pytest tests/ -q             # Unit-Tests
```

Voraussetzung für Antwort/PageIndex: LM Studio mit einem geladenen Instruct-Modell
(Port 1234). Empfohlen ein schnelles Nicht-Reasoning-Modell.
