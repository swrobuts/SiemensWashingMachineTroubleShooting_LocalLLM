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
