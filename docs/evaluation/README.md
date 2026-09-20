# Messprotokolle

Stand 19.09.2026. Reale Suche am mitgelieferten Siemens-Handbuch.
Embedding: multilingual-e5-small. Reranker: bge-reranker-v2-m3.

Die drei Suchvarianten verwenden denselben aktualisierten Index. Die Dateien
messen Keyword-Proxys für zehn Fragen, keine generierten Antworten. Laufzeiten
enthalten unterschiedliche Aufwärmeffekte. Details im [Prüfbericht](../AUDIT.md).

`negative-checks.json` enthält vier initiale Gegenbeispiele vor Parser-Version md-v5.
Die aktuelle Ablehnung ungeeigneter Fragen ist im Live-Prüfbericht dokumentiert.


Die aktuelle Messung nutzt Parser-Version `md-v5-procedure-context`. Bewertet
werden Top-k-Suchkandidaten vor dem relativen Antwortkontextfilter und der
Erweiterung kuratierter Arbeitsanleitungen. Sie ist daher kein Maß für die
endgültig an das LLM übergebene Evidenzmenge.

[Live-Prüfung von Antworten, Vorlesen und Handy-Anleitung](LIVE.md).

## PageIndex (vectorless)

Stand 20.09.2026, `eval/run_eval_pageindex.py`, dieselben zehn Fragen und derselbe
Stichwort-Proxy; Auswahlmodell gemma-4-12b-it-mlx in LM Studio auf einem Mac.
Bewertet werden die ausgewählten ganzen Abschnitte vor dem Kontextbudget.

| Protokoll | Stand | Treffer | hit@1 | MRR | Abdeckung | Ø Zeit/Frage |
|---|---|---|---|---|---|---|
| `pageindex-baseline.json` | flache Auswahl, englische Summaries, Batch 30 | 10/10 | 6/10 | 0,75 | 81 % | 57 s kalt (13 s mit Prompt-Cache) |
| `pageindex.json` | Fehlercode-Vorfilter, deutsche Stichwort-Kurzfassungen, Batch 30 | 10/10 | 8/10 | 0,88 | 92 % | 49 s (Fehlercode-Fragen 0 s, freie Fragen 52–67 s) |

Zum Vergleich Hybrid + Reranker (`mac-hybrid-rerank.json`): 10/10, 10/10, 1,00, 93 %,
0,6 s. Die Zeit der PageIndex-Auswahl hängt an den gelesenen Tokens (rund 10 000
je freier Frage bei etwa 200 Tokens/s), nicht an der Zahl der Aufrufe; kürzere
Summaries allein änderten am Ergebnis nichts (Vorabmessung: Summary 80 Zeichen
7/10 hit@1, 50 s). Der Gewinn kam aus den stichwortdichten deutschen Kurzfassungen,
der Zeitgewinn aus dem Vorfilter für Fehlercodes. Der Proxy misst keine
Antwortkorrektheit; der strukturelle Vorteil ganzer Arbeitsanleitungen ohne
Chunk-Schnitt ist darin nicht enthalten.
