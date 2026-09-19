# Ergänzende Mac-Prüfung am 19.09.2026

Ausgangscommit: `700431f`. Geprüft wurden der gemeldete Browserfehler, die
Retrieval-/Anbieteranbindung, die Antwortanzeige und die mobile Übertragung.
Dies ist eine gezielte Bugprüfung mit Live-Stichproben, kein Nachweis allgemeiner
Antwortkorrektheit.

## Ursachen und Korrekturen

- Die Hybrid-Suche brach vor dem Antwortmodell mit `JSONDecodeError` ab.
  Unter `.cache/embeddings` waren die Snapshot-Dateien des E5-Modells leer,
  einschließlich `modules.json`, Tokenizer und Modellgewichten. Der Projektordner
  wird über OneDrive synchronisiert; die vorhandene `.venv` ist eine
  Windows-Umgebung. Modell-Caches und virtuelle Umgebungen sind keine portablen
  Projektartefakte.
- `get_embed_model` verwendet jetzt `HF_HUB_CACHE`, statt einen Cache im
  Projektordner zu erzwingen. `HF_HOME`/`HF_HUB_CACHE` werden damit berücksichtigt.
  Die beschädigten lokalen Dateien wurden gesichert und durch vollständig
  heruntergeladene Dateien ersetzt, damit auch der bereits laufende Server ohne
  Neustart und Verlust des Sitzungsschlüssels wieder arbeiten kann.
- Bei einer OpenAI-Antwort zu E:23 war nur `tts_summary` befüllt. Die Oberfläche
  zeigte eine leere Antwortkarte. Sie zeigt nun bei leerem Detailinhalt die
  Zusammenfassung an; HTML bleibt maskiert. Vollständige Schrittlisten bleiben
  unverändert.
- LM Studio bot drei Chatmodelle an, weshalb die automatische Auswahl nicht
  eindeutig war. Das tatsächlich geladene `gemma-4-12b-it-mlx` wurde in der
  ignorierten lokalen Profildatei eingetragen. Keine Zugangsdaten wurden in
  Projektdateien übernommen.
- Die scheinbar zahlreichen Git-Änderungen waren überwiegend veränderte
  Ausführbarkeitsbits. Die Dateimodi wurden auf den vorhandenen Git-Stand
  zurückgesetzt. Die bereits vor dieser Prüfung geänderte Präsentation unter
  `docs/slides/` mit 60 Folien blieb unverändert erhalten; ihr ZIP-Container wurde
  auf Integrität geprüft. Der ältere Export im Projektstamm bleibt erhalten.

## Nachweise

- 86 Python-Tests bestanden; 14 JavaScript-Tests bestanden.
- Neue Regressionstests reproduzierten zunächst den beschädigten Projektcache
  und die unsichtbare Kurzantwort. Nach der Korrektur bestanden sie.
- Ein unabhängiger Code-Review meldete keine weiteren Befunde an diesen Änderungen.
- Reale Hybrid-Suche: 10/10 Stichworttreffer in Top 5 und auf Rang 1; MRR 1,0,
  Stichwortabdeckung 93,5 %. Rohwerte: [mac-hybrid-rerank.json](mac-hybrid-rerank.json).
  Die Messung bewertet Kandidaten vor dem Antwort-Kontextfilter, keine fachliche
  Korrektheit generierter Antworten.
- LM Studio, `/api/ask`, Hybrid, „Was bedeutet E:23?“: Antwort mit Wasser in der
  Bodenwanne, Wasserhahn schließen und Kundendienst rufen. Laufzeit etwa 21,5 s.
- LM Studio, Hybrid, „Was bedeutet E:999?“: ausdrückliche Ablehnung statt
  Übernahme eines ähnlichen Fehlercodes, etwa 1,4 s.
- OpenAI im bestehenden Edge-Browser, Hybrid, E:23: Antwort empfangen und nach
  der Frontend-Korrektur sichtbar; gemeldet wurden 334 Eingabe-/58 Ausgabetokens.
- OpenAI im Browser, PageIndex, E:23: Bedeutung und zwei Schritte (Wasserhahn
  schließen, Kundendienst rufen), drei Originalauszüge; 1239 Eingabe-/104
  Ausgabetokens der Antwort. Navigationsaufrufe sind darin nicht enthalten.
- QR-Code erzeugt und den daraus erzeugten Link im Browser geöffnet: Die
  öffentliche mobile Leseseite zeigte dieselbe Zusammenfassung und beide
  Schritte. Kein physischer Handy-Scan oder akustischer Hörtest durchgeführt.

Die OpenAI-Tests verwendeten ausschließlich den bereits im Server-Arbeitsspeicher
hinterlegten Sitzungsschlüssel. Der Server wurde nicht neu gestartet. Der neue
Standard-Cachepfad gilt für neue Python-Prozesse; die vorhandene Serverinstanz
verwendet bis dahin den reparierten bisherigen Cache.

## Grenzen und Umgebung

„Wasser schießt aus der Maschine“ verursacht nach der Cache-Reparatur keinen
technischen Fehler mehr, erreicht aber keinen ausreichenden Relevanzwert und
wird abgelehnt. „Wasser läuft aus“ findet dagegen die einschlägigen Stellen
(Top-Score etwa 0,979). Die Schwelle wurde nicht abgesenkt. Die Sensitivität
gegenüber Formulierungen bleibt eine bekannte Retrieval-Grenze.

Getestet mit der bereits laufenden Mac-Installation: Python 3.12.12, torch 2.12.1,
transformers 5.8.1, sentence-transformers 5.6.0, llama-index-core 0.14.23,
llama-index-embeddings-huggingface 0.7.0, openai 2.21.0 und Flask 3.1.2.
Dies ist keine Neuinstallation der in `requirements.txt` fixierten Versionen.
Die früheren Windows-Prüfprotokolle bleiben separat erhalten.

```sh
python -m pytest -q
node --test tests/*.test.cjs
python eval/run_eval.py --output .audit/mac-hybrid-rerank.json --min-hit-rate 1
```
