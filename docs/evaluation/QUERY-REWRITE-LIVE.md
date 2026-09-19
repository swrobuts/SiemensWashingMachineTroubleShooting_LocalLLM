# LLM-Suchumformulierung: Prüfung am 19.09.2026

Ausgangscommit: `5a3f74c`. Ziel ist die Bearbeitung von Umgangssprache und
Tippfehlern wie „Wasser schießt aus der Maxchine“ auch dann, wenn die erste
Hybrid-Suche keinen ausreichend relevanten Treffer findet.

## Ablauf und Grenzen

Die vorhandene Suche bleibt der erste Versuch. Nur bei einem unbelegten Ergebnis
ohne expliziten Fehlercode formuliert das gewählte LLM eine kurze, übliche
Störungsbeschreibung. Danach wird genau einmal mit denselben Such- und
Relevanzregeln erneut gesucht. Originalfrage und gefundene Handbuchauszüge gehen
an die Antwortgenerierung. Die GUI zeigt die Suchformulierung separat an.

Das LLM soll keine Ursache oder Reparatur erfinden. Der Parser begrenzt Länge,
Format und Zahlen; Fehlercodes werden nicht umgedeutet. Ungültige Antworten und
nicht verfügbare Umformulierungsmodelle erhalten die ursprüngliche Ablehnung.
Auch eine gültige Umformulierung muss die Relevanzprüfung bestehen. Die
semantische Sinnwahrung ist weiterhin eine Modellleistung und nicht garantiert.

Dieser Mechanismus gilt für Hybrid. PageIndex verwendet bereits eine
LLM-gestützte Abschnittsauswahl. Zusätzliche Suchaufrufe kosten Zeit und bei
OpenAI API-Gebühren; die Tokenanzeige zählt nur die Antwortgenerierung und
weist nun ausdrücklich auf die nicht mitgezählten Suchaufrufe hin.

## Automatische Prüfung

106 Python-Tests und 15 JavaScript-Tests bestanden. Neue Tests prüfen:

- Einen einzigen Suchwiederholungsversuch, ohne rekursive Schleife.
- Kein Umformulierungsaufruf bei einem guten Ersttreffer oder bei Fehlercodes.
- Ablehnung leerer, zu langer, ungültiger und um Fehlercodes ergänzter Ausgaben.
- JSON-Codeblöcke, wie sie das lokale Modell im Live-Test tatsächlich lieferte.
- Verhalten bei einem nicht verfügbaren Modell.
- Durchreichen des gewählten Anbieters/Sitzungsschlüssels und Schließen des
  kurzlebigen OpenAI-Clients.
- Originalfrage in der Antwortgenerierung und `search_query` im JSON-/SSE-Ergebnis.
- Sichere Anzeige der Suchformulierung als Text.

Neue Tests wurden vor ihren jeweiligen Korrekturen fehlschlagen gesehen.
Ein unabhängiger Code-Review fand keine weiteren Probleme.

## Live-Stichproben

Modell: LM Studio `gemma-4-12b-it-mlx`, Hybrid-Suche mit E5 und BGE-Reranker.
Die bestehende Python-Umgebung entspricht der im [Mac-Protokoll](MAC-LIVE.md).

| Originalfrage | Beobachtete Suchumformulierung |
|---|---|
| Wasser schießt aus der Maxchine | Wasser läuft aus |
| Aus meiner Waschmaschiene spritzt Wasser | Wasser läuft aus |
| Es kommt kein Wasser in die Maschiene | Wasser läuft nicht ein |

Ende-zu-Ende-Ergebnis im geöffneten Browser: Die genaue Originalfrage
„Wasser schießt aus der Maxchine“ zeigte „Gesucht nach: Wasser läuft aus“ sowie
die Maßnahmen aus der Störungstabelle und den Hinweis zum Sichern des
Ablaufschlauchs. Zwei Handbuchauszüge, 438 Eingabe-/168 Ausgabetokens der Antwort.

Über die laufende JSON-API lieferte „Aus meiner Waschmaschiene spritzt Wasser“
dieselbe passende Störungstabelle (Top-Score 0,979) und eine belegte Antwort,
Laufzeit 31,3 Sekunden. „Was ist die Hauptstadt von Frankreich?“ wurde nach
1,5 Sekunden abgelehnt, „Was bedeutet E:999?“ nach 0,3 Sekunden. Es wurde weder
eine allgemeine Wissensantwort noch eine fremde Fehlercodebedeutung ausgegeben.

Die letzte Zeile prüft die Sinnwahrung der Umformulierung, nicht die vollständige
Antwortqualität bei fehlendem Wasserzulauf. Die Prüfung ist eine kleine,
gezielte Stichprobe und keine Aussage über beliebige Formulierungen.

Für die Aktivierung des geänderten Python-Codes wurde der lokale Server neu
gestartet. Dabei erlosch der bisherige OpenAI-Sitzungsschlüssel wie vorgesehen.
Die neue Umformulierung wurde lokal live getestet; der OpenAI-Pfad wurde in
isolierten Routing-/Client-Lebensdauer-Tests geprüft, nicht mit einem neuen
Live-Key. Für OpenAI muss ein Schlüssel erneut in der Oberfläche eingegeben werden.
