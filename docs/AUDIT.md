# Prüfbericht vom 19.09.2026

## Umfang und Ausgangslage

Geprüft wurde das vorhandene Repository
[SiemensWashingMachineTroubleShooting_LocalLLM](https://github.com/swrobuts/SiemensWashingMachineTroubleShooting_LocalLLM),
Ausgangscommit `a8d9cc4046ed0168561b73879f328e34549a0627`.
Die zweite Projektablage enthielt Konfiguration und IDE-Daten, aber keine zweite
prüfbare Codebasis. Der endgültige Stand führt beide Anbieter in **einer App**
zusammen und erhält die bestehende Git-Historie.

Python 3.12.14 unter Windows. Prüfung des Quellcodes, Regressionstests,
Modellmessungen am echten Handbuch, exemplarische PDF-Neuverarbeitung und
Bedienprüfung des GUI. Das ist kein vollständiges formales Sicherheitsaudit
und keine fachliche Freigabe für beliebige Maschinenreparaturen.

## Behobene Fehler und Verbesserungen

| Befund | Änderung und Nachweis |
|---|---|
| Fehlende Server-/Parser-/CLI-Dateien im Arbeitsverzeichnis | Aus dem vorhandenen Git-Stand wiederhergestellt und anschließend überarbeitet |
| Kein gemeinsamer lokaler/API-Betrieb | Eine Flask-App, Anbieter-Toggle und getrennte Clients pro Anbieter; Routing- und HTTP-Vertragstest |
| Beliebige Projektdateien über statische Route erreichbar | Explizite Freigabe von HTML, Logo und QR-Script; Regressionstests für private Pfade |
| Nicht maskierte dynamische HTML-Inhalte | Zeichenmaskierung vor Formatierung, Quelltexte per textContent |
| Retrieval-Ausnahmen und Streamabbrüche uneinheitlich | JSON-/SSE-Fehlerbehandlung, Abbruch veralteter Anfragen, Erkennung fehlender finaler Ergebnisse |
| Modell-Output am Tokenlimit konnte als fertig gelten | Abgeschnittene Antworten werden verworfen |
| Fehlende Eingabe- und Größenprüfung | JSON-Schema-Grundprüfung, 2000 Zeichen, 16-KiB-Body |
| Fehlercode-Lookup traf Teilzeichenfolgen | Vollständige normalisierte Codes; E:18 und E:180 getrennt |
| Große Abschnitte überschritten Embedding-Kontext | 440-Token-Chunks, 40 Overlap, E5-Tokenizer und Limitprüfung |
| Mehrere Tabellen / Fortsetzungszeilen verloren Struktur | Pro Tabelle eigener Header, Zeilenkontext erhalten |
| Unsichere Annahme über Score-Skala | Sigmoid beim BGE-Reranker explizit gesetzt; Vektorscores separat behandelt |
| Alte Indizes blieben bei Parameterwechsel möglich | Cache-Fingerprint erweitert; FileLock; defekte Caches neu aufbauen |
| Querverweise erschienen wie Fundseiten | Echte PDF-Seiten nur bei Metadaten, alte Verweise klar als Querverweise bezeichnet |
| PageIndex akzeptierte unzuverlässige ID-Extraktion | JSON-Auswahl, IDs auf aktuellen Batch beschränkt, leere Texte ausgeschlossen |
| PageIndex bevorzugte frühe Kapitel | Globale Auswahl aus den Batch-Kandidaten statt bloßem Abschneiden |
| Baum konnte zu anderer Wissensdatei gehören | Quellhash im Baum und Prüfung beim Laden |
| Allgemeine Modelltipps als Internetwissen bezeichnet | Gemeinsamer Prompt fordert ausschließlich Handbuchkontext; keine behauptete Websuche |
| Feste Zahlen im GUI wirkten wie aktuelle Benchmarks | Entfernt; tatsächliche Messungen in diesem Bericht |
| Veraltete Abhängigkeiten und PyPDF2-Imports | Versionen aktualisiert, kompatibel fixiert und pip check ausgeführt |
| Abhängigkeit von externem QR-Script beim Start | Script und Lizenz lokal eingebunden |
| Getrennte Dokumentation und duplizierte Notebook-Logik | Aktuelle gemeinsame Anleitung; Notebook importiert die Anwendungsfunktionen |

## Prüfresultate

- **85 Python-Tests und 12 JavaScript-Tests bestanden.** Logik, private Dateirouten, fehlerhafte
  Eingaben, JSON/SSE, Antwortformat, Tokenabbruch, Provider-Isolation und
  OpenAI-kompatibler HTTP-Vertrag zu einem lokalen Testserver.
- **Schlüsselschutz:** Sitzungsisolation, Entfernung, Ablauf, Neustart, CSRF,
  Host-/Origin-Sperre sowie kein Key in Cookie, Antwort oder Fehlerprotokoll geprüft.
- **Git-Inhalt:** Zur Synchronisation vorgesehene Projektdateien einschließlich
  entpackter DOCX-/PPTX-Inhalte und PDF-Text auf OpenAI-Schlüssel-Muster geprüft:
  kein Fund. Lokale Schlüsselarchive, Caches und Konfigurationen sind ausgeschlossen.
- **pip check:** keine inkonsistenten installierten Abhängigkeiten.
- **Initiale GUI-Prüfung:** Umschalten zwischen lokal / OpenAI sichtbar geprüft. Passwortfeld mit
  einem unechten Testwert geprüft, nach Übernahme leer, Entfernen deaktiviert OpenAI.
  Die neu gestaltete Registerkarte dokumentiert Ingestion, beide Retrieval-Pipelines,
  Modelladapter, API-Vertrag, Provenienz und gemessene Retrieval-Metriken. Kein echter Key
  wurde für diese UI-Prüfung eingesetzt.
- **PDF:** 48 Seiten. Physische Seite 33 erneut mit Docling verarbeitet.
  E:18 erhält Pumpe/Ablauf und Querverweise 30/31. E:23 erhält
  Wasser in der Bodenwanne, Wasserhahn schließen und Kundendienst (Verweis 36).
  Die Einzelseiten-Testdatei trägt korrekterweise den Seitenmarker 1.
- **PageIndex-Inhalt:** alle 187 vorhandenen Node-Texte sind im aktiven Markdown
  enthalten. Der Quellhash stimmt mit der Wissensdatei überein.
- **OpenAI-Verbindung:** eine kurze Verbindungskontrolle mit gpt-4.1-mini
  gelang. Das prüft noch keine handbuchbasierte Antwort.
- **Reale lokale LLM-Antworten:** nicht geprüft, weil der LM-Studio-Server auf
  dem Mac aus dieser Windows-Umgebung nicht erreichbar war.
- **OpenAI-Live-Prüfung:** vom Nutzer freigegeben und über die Browsersitzung ausgeführt.
  Der ergänzende [Live-Prüfbericht](evaluation/LIVE.md) dokumentiert Fälle und Grenzen.

### Reale Retrieval-Messung

Alle drei Varianten verwenden dieselbe überarbeitete Aufbereitung und denselben
E5-Index. Dies ist eine Ablation der Suchkomponenten, **kein vollständiger
Vorher-/Nachher-Vergleich des alten Projekts**. Zehn Fragen, zwölf Vektorkandidaten
und fünf Kandidaten vor Antwortkontextfilter und Erweiterung der Arbeitsanleitungen.
Die Messung wurde nach der Ergänzung der Arbeitskontexte erneut ausgeführt.

| Variante | Keyword-Hit@5 | Keyword-Hit@1 | Keyword-MRR | Keyword-Abdeckung |
|---|---:|---:|---:|---:|
| Vektor allein | 80 % | 60 % | 0,700 | 64,5 % |
| Hybrid ohne Reranker | 90 % | 70 % | 0,800 | 82,0 % |
| Hybrid mit Reranker | 100 % | 100 % | 1,000 | 93,5 % |

[Vector](evaluation/vector.json),
[Hybrid ohne Reranker](evaluation/hybrid-no-rerank.json),
[Hybrid mit Reranker](evaluation/hybrid-rerank.json).

Ein Treffer bedeutet mindestens ein erwartetes Stichwort in den Ergebnissen.
Keyword-MRR mittelt den Kehrwert des ersten Stichworttrefferrangs.
Keyword-Abdeckung misst den Anteil gefundener erwarteter Wörter.
Das sind Such-Proxys, keine Beurteilung generierter Antworten und kein
vollständiger Dokument-Recall. Unterschiedliche Aufwärmzustände beeinflussen
die aufgezeichneten Laufzeiten; diese dienen hier nicht als Geschwindigkeitsbenchmark.

### Initiale Gegenbeispiele mit echtem Reranker

| Frage | Höchster Score | Ergebnis |
|---|---:|---|
| Hauptstadt Frankreichs | 0,000071 | Abgelehnt |
| Gedicht über den Mond | 0,000302 | Abgelehnt |
| Unbekannter Code E:180 | 0,000267 | Abgelehnt |
| Motor einer Bosch-Spülmaschine | 0,027354 | Abgelehnt |

[Messprotokoll](evaluation/negative-checks.json), vor Parser-Version md-v5.
Aktuelle Live-Gegenproben: [LIVE.md](evaluation/LIVE.md). Vier Beispiele sind keine
allgemeine Garantie gegen falsche Antworten oder Prompt-Injection.

## Getestete Abhängigkeiten

| Komponente | Version |
|---|---|
| Flask | 3.1.3 |
| LlamaIndex Core | 0.14.24 |
| LlamaIndex HuggingFace Embeddings | 0.8.0 |
| Sentence Transformers | 6.1.0 |
| Transformers | 5.17.0 |
| PyTorch | 2.14.0 |
| OpenAI SDK | 2.54.0 |
| Docling (optional) | 2.129.0 |
| LiteLLM (optional) | 1.101.0 |
| PyMuPDF / pypdf (optional) | 1.28.2 / 6.19.0 |
| pytest | 9.1.1 |

Die OpenAI-SDK-Version ist auf den mit LiteLLM kompatiblen Stand fixiert.
[requirements-lock.txt](../requirements-lock.txt) dokumentiert die aufgelöste
Windows-Umgebung. Der pywin32-Eintrag ist auf Windows beschränkt.
Das Lockfile ist kein Nachweis, dass alle Pakete bereits auf dem konkreten
Apple-Silicon-Mac getestet wurden.

## Lokale Konsolidierung und Zugangsdaten

Die alte Konfiguration und IDE-Daten wurden verlustfrei im ignorierten lokalen
Archiv .audit/original-folder gesichert. Der ursprüngliche Ordner ist leer,
konnte wegen einer Betriebssystem-Sperre aber noch nicht entfernt werden.
Das Archiv gehört nicht zum GitHub-Inhalt. Ein früher angelegtes OpenAI-Profil
mit Key liegt ebenfalls nur im lokalen Archiv und wird von der App nicht gelesen.
Für die aktuelle Nutzung ist die Eingabe über das GUI erforderlich.

## Verbleibende Grenzen

1. Tatsächliches LM-Studio-Modell, Kontextfenster und Leistung am Mac prüfen.
2. Die Antworttreue braucht einen größeren fachlich annotierten Testbestand.
3. Das bestehende Markdown enthält OCR-Artefakte; eine vollständige neue
   Extraktion muss gegen Tabellen, Symbole und Warnungen geprüft werden.
4. PageIndex bewertet gültige Auswahl-IDs und vorhandenen Text, bietet aber
   keinen gleichwertig kalibrierten semantischen Relevanzfilter.
5. Das Zeichenbudget für Kontext ist kein exakter Tokenzähler des Antwortmodells.
6. Eine öffentliche RAG-API benötigt Anmeldung und Betriebsgrenzen. Die lokale
   API bleibt auf 127.0.0.1. GitHub Pages veröffentlicht ausschließlich die statische
   Handy-Leseseite ohne Schlüssel und ohne KI-Endpunkt.


## Im Live-Test zusätzlich gefundene Fehler

- Windows-Konsolenkodierung: Emoji-Ausgaben konnten den Indexstart mit
  UnicodeEncodeError abbrechen. Bibliotheks-Logging ersetzt die direkten Prints.
  Cache-Treffer, Neuaufbau und Cache-Reparatur sind unter cp1252 getestet.
- PageIndex-Kontextgröße: Mehrere vollständige Tabellen konnten das 14.000-Zeichen-
  Budget überschreiten. Die Auswahl packt nun vollständige Abschnitte in das
  Budget und zeigt nur übergebene Quellen. Keine stille Textkürzung.
- Antwortformat: Wiederholte manual_steps-Tags verloren zuvor spätere Schritte.
  Der Parser sammelt alle Blöcke. Die Checklisten-Konvertierung erhält Fettdruck.
- Fehlender Arbeitskontext: Die Pumpensuche trennte Warnung und Reinigung und
  bezog Transportvorbereitung ein. Vier kuratierte Kontextgruppen, kontextbezogene
  Chunk-Metadaten, vollständige Verfahrensbelege und ein relativer Scorefilter
  beheben den reproduzierten Fall. Das ist keine generelle Sicherheitsgarantie.
- Vorlesen: Vollständige Schritte statt nur Zusammenfassung, abgesicherte
  Browser-Unterstützung, Start-/Ende-/Fehleranzeige und abbrechbare Kurzabschnitte.
- QR-Code: Die Antwort ersetzt den bisherigen localhost-Fragelink. Eine separat
  veröffentlichte Leseseite stellt Schritte grafisch dar; Schlüssel werden nicht
  übertragen. Große Antworten bleiben über HTML-Export vollständig erhalten.
