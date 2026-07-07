# Design: Optimierung der Troubleshooting-Pipeline

**Datum:** 2026-07-07
**Ziel:** Erkennung, Verarbeitung und Antwort des lokalen Siemens-Waschmaschinen-
Assistenten deutlich verbessern — bei voller Lokalität (LM Studio + lokale
Embeddings, keine Cloud, DSGVO-konform).

## Ausgangslage

- `parser.py` — Docling: `siemens-handbuch.pdf` → `siemens_wissen.md` (bleibt).
- `server.py` — Flask (Port 3001), LlamaIndex-RAG: `MarkdownNodeParser` →
  `VectorStoreIndex` (in-memory), Embedding `intfloat/multilingual-e5-small`,
  lokales LM Studio-LLM, XML-strukturierte Antwort.
- `lokale_ki.py` — Dev-Scratch (Bug: Index aus `documents` statt `nodes`).
- `index.html` — Single-File-Frontend, POST `/api/ask`, Rückfrage als String-Hack.
- `siemens_wissen.md` — 12k Wörter, 187 `##`-Überschriften (teils OCR-Rauschen),
  189 Tabellenzeilen, Fehlercodes nur `E:18`/`E:23`.

## Kernbefunde

1. **e5 ohne Präfixe** — `multilingual-e5-small` verlangt `query:`/`passage:`-
   Präfixe; fehlen → schlechtere Treffer. Größter einzelner Retrieval-Verlust.
2. **Kein Reranking, kein Similarity-Cutoff** (`similarity_top_k=6`).
3. **Index bei jedem Start neu embedded** — keine Persistenz.
4. **Schwächste e5-Stufe** — `e5-base`/`bge-m3` heben deutsche Qualität.
5. **Kein Streaming** — Query blockiert (Timeout bis 1200 s), nur Spinner.
6. **Keine Quellenzitate** trotz `source_nodes`; `reference` hart verdrahtet.
7. **Kein Grounding-Guardrail** — halluziniert bei schwachen Treffern.
8. **Rückfrage = Frontend-Hack** — vorige Frage wird mitembeddet.
9. **Kein Eval-Set** — „besser" nicht messbar.

## Nicht-Ziele / Entscheidungen

- **Docling bleibt** als Extraktion.
- **PageIndex: nein** — 115 KB sind für gutes Chunking + Reranking zu klein;
  Aufwand lohnt erst bei viel größeren Handbüchern.
- **Cloud: nein** — alles bleibt lokal.

## Architektur-Zielbild

`server.py` wird in eine **importierbare RAG-Schicht** (`rag_engine.py`) und die
Flask-Hülle getrennt. So kann das Eval-Set den Query-Engine ohne Flask/LLM-
Abhängigkeit (bzw. mit Stub) testen. Der Index wird auf Platte **persistiert**
und nur neu gebaut, wenn sich Quelle (`siemens_wissen.md`) oder Embedding-Konfig
ändern (Invalidierung via Hash-Marker).

## Phasen (je eigener Commit, TDD)

### Phase 0 — Fundament & Messung
- **e5-Präfix-Fix**: `HuggingFaceEmbedding(query_instruction="query: ",
  text_instruction="passage: ")`.
- **Index-Persistenz** mit Invalidierung (Hash aus Quelldatei + Embedding-Name).
- **Refactor**: `rag_engine.py` (build/load index, query engine) getrennt von Flask.
- **Eval-Set**: `eval/questions.json` (reale Störungsfragen → erwartete
  Handbuch-Stichwörter/Abschnitte) + Runner `eval/run_eval.py` (Retrieval-
  Trefferquote). Läuft auf der Zielmaschine (LM Studio + Modelle).
- **requirements.txt** ergänzen (Reproduzierbarkeit).

### Phase 1 — Verarbeitung (Retrieval)
- Embedding-Upgrade (`e5-base` oder `bge-m3`, ENV-konfigurierbar).
- **Reranking** (lokaler `bge-reranker`/CrossEncoder) über Top-k.
- **Similarity-Cutoff** (Postprocessor) gegen Rausch-Nodes.
- Saubereres Chunking (Node-Größe steuern, OCR-Rausch-Header entschärfen).

### Phase 2 — Antwort (Generierung + UX)
- **Streaming** (SSE) statt Blocking-Query.
- **Quellenzitate** aus `source_nodes` (Abschnitt/Position) → `reference`.
- **Grounding-Guardrail**: bei schwachen Treffern „nicht im Handbuch gefunden".
- Robusteres Structured-Output.

### Phase 3 — Erkennung / Dialog
- Fehlercode-Normalisierung serverseitig (`E23`/`E:23`/„Fehler 23").
- Echte serverseitige Mehrturn-Historie (Frontend-Hack ersetzen).

### Phase 4 — Politur
- `lokale_ki.py` aufräumen/entfernen, README, Doku.

## Umsetzungsstand (2026-07-07)

Gemessen auf der Zielmaschine (LM Studio, lokale Modelle):

- **Phase 0 ✅** e5-Präfix-Fix, persistenter Index (Hash-Invalidierung), Eval-Harness.
- **Phase 1 ✅** Reranking (bge-reranker-v2-m3), zeilenweises Tabellen-Chunking,
  Hybrid-Fehlercode-Lookup. **Retrieval: Recall 64 %→96 %, MRR 0.73→1.00,
  hit@1 70 %→100 %** (10 reale Störungsfragen, `eval/run_eval.py`).
- **Phase 2a ✅** Echte Quellenzitate aus genutzten Abschnitten (`… · Seite NN`).
- **Phase 2b ✅** Token-Streaming via SSE (`/api/ask_stream`) — LLM direkt
  gestreamt (der LlamaIndex-Query-Engine-Streaming-Pfad puffert). Frontend zeigt
  Quelle nach ~1 s und die Antwort live. Verifiziert: Quelle @1,3 s, 1. Token @7,2 s.
- **LLM-Fix ✅** OpenAILike + explizites Modell. **Default `gemma-4-12b-it-mlx`**
  (Nicht-Reasoning): ~40 s statt ~250 s beim 27B-Reasoning-Modell.

**Zentraler Befund:** Für die *Antwort*-Latenz dominiert die **Modellwahl**.
Reasoning-Modelle „denken" lange (`reasoning_content`) → 250 s; ein schnelles
Instruct-Modell + Streaming ist für den Kiosk deutlich besser.

- **Guardrail ✅** Anti-Halluzination: kalibriert am Reranker-Score (In-Scope
  ≥ 0.435, Out-of-Scope ≈ 0.0 → Schwelle `GUARDRAIL_MIN_SCORE=0.15`). Nicht
  gedeckte Fragen → „nicht im Handbuch" ohne LLM-Aufruf. Zusätzlich Prompt-
  Ehrlichkeit für Rand-Fälle. Verifiziert (Kuchen-Frage → Absage; kein LLM).
- **Phase 4 ✅** `lokale_ki.py` → sauberes CLI, README.

### Offen (optional)
- **Echte Mehrturn-Historie** serverseitig (der Frontend-String-Hack lebt noch).

## Verifikation

End-to-End (Retrieval-Qualität, LLM-Antwort) braucht die Zielmaschine mit LM
Studio + heruntergeladenen Modellen. Im Repo verifizierbar sind: Präfix-/Konfig-
Korrektheit, Persistenz-/Invalidierungslogik (mit Stub-Embedding) und die Eval-
Mechanik. Qualitätssprünge werden über das Eval-Set vorher/nachher belegt.
