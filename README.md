# Siemens Waschmaschine — Lokaler Troubleshooting-Assistent

Ein **komplett lokaler** RAG-Assistent (DSGVO-konform, keine Cloud): stellt Fragen
zu einer Siemens-Waschmaschine und beantwortet sie aus dem offiziellen Handbuch —
mit Quellenangabe (Abschnitt + Seite). Läuft gegen ein lokales LLM in **LM Studio**.

## Dokumentation

- **[docs/TECHNICAL.md](docs/TECHNICAL.md)** — technische Doku mit Schwerpunkt auf der
  Dokumentenaufbereitung (Docling → Chunking → Embeddings → Index → Retrieval).
- **[notebooks/document_processing_pipeline.ipynb](notebooks/document_processing_pipeline.ipynb)**
  — die Dokumentenverarbeitungs-Pipeline als eigenständiges, in Google Colab
  lauffähiges Notebook (in Colab: *Datei → Notebook hochladen*).
- **[docs/2026-07-07-optimization-design.md](docs/2026-07-07-optimization-design.md)**
  — Design- und Statusdokument der Optimierungen.

## Architektur

```
siemens-handbuch.pdf
      │  parser.py  (Docling: PDF → strukturiertes Markdown)
      ▼
siemens_wissen.md
      │  rag_engine.py
      │   • lokale Embeddings (multilingual-e5, mit query:/passage:-Präfixen)
      │   • zeilenweises Tabellen-Chunking (Fehlercodes einzeln auffindbar)
      │   • persistenter Vektorindex (storage/)
      │   • Hybrid-Retriever: Vektor-Overfetch + exakter Fehlercode-Lookup
      │   • Cross-Encoder-Reranking (bge-reranker-v2-m3)
      │   • Quellenzitat aus genutzten Abschnitten
      ▼
   ┌─────────────────────────────┬────────────────────────────┐
   │ server.py (Flask, :3001)    │ lokale_ki.py (Terminal-CLI) │
   │  /api/ask         (JSON)    │                            │
   │  /api/ask_stream  (SSE)     │                            │
   └─────────────┬───────────────┴────────────────────────────┘
                 ▼
          index.html  (Frontend: Live-Streaming, TTS, QR)
```

## Voraussetzungen

- Python 3.12
- [LM Studio](https://lmstudio.ai/) mit einem geladenen Instruct-Modell (Port 1234).
  Empfohlen: ein **schnelles Nicht-Reasoning-Modell** (z. B. `gemma-4-12b-it-mlx`).
  Reasoning-Modelle „denken" lange und sind für den interaktiven Einsatz zu langsam.

```bash
pip install -r requirements.txt
```

## Nutzung

**1. Handbuch aufbereiten** (einmalig, wenn sich das PDF ändert):
```bash
python3 parser.py          # siemens-handbuch.pdf → siemens_wissen.md
```

**2a. Web-App:**
```bash
python3 server.py          # startet auf http://localhost:3001
```
Dann `index.html` im Browser öffnen. Die Quelle erscheint sofort, die Antwort
streamt live.

**2b. Terminal-CLI:**
```bash
python3 lokale_ki.py "Was bedeutet Fehler E:23?"
python3 lokale_ki.py       # interaktiver Modus
```

**3. Retrieval-Qualität messen** (braucht *kein* LM Studio):
```bash
python3 eval/run_eval.py                 # Hybrid + Reranking
python3 eval/run_eval.py --no-rerank     # nur Vektor (A/B-Vergleich)
```

## Konfiguration (ENV)

| Variable | Default | Zweck |
|----------|---------|-------|
| `LOCAL_LLM_MODEL` | `gemma-4-12b-it-mlx` | Modellname in LM Studio |
| `LOCAL_LLM_ENDPOINT` | `http://127.0.0.1:1234/v1` | LM-Studio-Endpoint |
| `EMBED_MODEL` | `intfloat/multilingual-e5-small` | lokales Embedding (Index rebuildet bei Wechsel) |
| `RERANK_MODEL` | `BAAI/bge-reranker-v2-m3` | Cross-Encoder-Reranker |
| `ENABLE_RERANK` | `1` | `0` = Reranking aus |
| `RETRIEVE_K` / `FINAL_K` | `12` / `5` | Overfetch bzw. finale Abschnitte |
| `GUARDRAIL_MIN_SCORE` | `0.15` | Mindest-Reranker-Score; darunter „nicht im Handbuch" statt Antwort |

## Ergebnisse (Retrieval-Eval, 10 reale Störungsfragen)

| Variante | Trefferquote | hit@1 | MRR | Ø Recall |
|---|---|---|---|---|
| Vektor-only (e5-Fix) | 80 % | 70 % | 0.73 | 64 % |
| + Reranking | 90 % | 80 % | 0.85 | 81 % |
| + Tabellen-Chunking + Fehlercode-Lookup | **100 %** | **100 %** | **1.00** | **96 %** |

## Tests

```bash
python3 -m pytest tests/ -q
```

## Projektstruktur

```
parser.py            Docling-Extraktion PDF → Markdown
rag_engine.py        RAG-Kern (Embeddings, Chunking, Hybrid-Retriever, Reranker, Zitat)
server.py            Flask-API (/api/ask, /api/ask_stream)
lokale_ki.py         Terminal-CLI
index.html           Frontend (Streaming, TTS, QR)
eval/                Retrieval-Eval (ohne LLM lauffähig)
tests/               Unit-Tests
docs/                Design- & Statusdokument
```

Lokales Lehr-/Forschungsprojekt. Nicht mit Siemens/BSH affiliiert.
