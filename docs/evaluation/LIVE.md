# Live-Prüfung am 19.09.2026

## Aufbau und Ergebnis

Sieben vorab festgelegte fachliche bzw. negative Fälle wurden über die laufende
Oberfläche auf `http://127.0.0.1:3001/` geprüft. Anbieter: OpenAI,
Antwortmodell: `gpt-4.1-mini`, Handbuch: die mitgelieferte Siemens-Anleitung.
Der API-Key wurde ausschließlich über die lokale Sitzung verwendet und gehört
nicht zu diesem Protokoll. Die Ergebnisse wurden mit den Originalauszügen verglichen.

Alle sieben Fälle erfüllten im abschließenden Durchlauf die unten genannten
Akzeptanzkriterien. Dies ist eine gezielte Stichprobe, keine statistisch belastbare
Fehlerquote und keine allgemeine Freigabe von Reparaturanleitungen.

| Modus / Frage | Akzeptanzkriterium und beobachtetes Ergebnis | Antwort-Tokens Eingang / Ausgang |
|---|---|---:|
| Hybrid: Wie reinige ich die Laugenpumpe? Welche Sicherheitsmaßnahmen sind vorher nötig? | Warnung vor heißer Lauge; abkühlen, Wasserhahn schließen, ausschalten und Netzstecker ziehen vor Reinigung; Entleerung, Pumpenreinigung, Montage und 1 Liter Wasser / Abpumpen enthalten. Keine Transportvorbereitung. Ein vollständiger Verfahrensbeleg. Bestanden. | 646 / 375 |
| Hybrid: Fehler E:18 | Beide Ursachen und Abhilfen: verstopfte Laugenpumpe reinigen sowie verstopfter Ablaufschlauch / Abflussrohr, Reinigung am Siphon. Querverweise 30 / 31. Bestanden. | 355 / 121 |
| Hybrid: Fehler E:23 | Wasser in der Bodenwanne / Undichtigkeit; Wasserhahn schließen und Kundendienst rufen, Querverweis 36. Bestanden. | 341 / 107 |
| Hybrid: Was bedeutet E:180? | Kein Rückgriff auf E:18; ausdrückliche Ablehnung „Nicht im Handbuch gefunden“. Bestanden. | Nicht gemeldet |
| Hybrid: Was ist die Hauptstadt von Frankreich? | Keine freie Wissensantwort; ausdrückliche Ablehnung. Bestanden. | Nicht gemeldet |
| PageIndex: Was bedeutet der Fehler E:23? | Wasser in der Bodenwanne / Undichtigkeit, Wasserhahn schließen und Kundendienst. Zwei übergebene Originalabschnitte. Bestanden. | 1227 / 102 |
| PageIndex: Was ist die Hauptstadt von Frankreich? | Keine freie Wissensantwort; ausdrückliche Ablehnung. Bestanden. | Nicht gemeldet |

Die Werte stammen aus der vom Antwortmodell gemeldeten Nutzung. Zusätzliche
PageIndex-Auswahlaufrufe sind nicht enthalten; fehlende Werte bedeuten nicht
„kostenlos“. Einzelläufe können bei erneuter Generierung anders formuliert sein.

## Fehler vor dem abschließenden Durchlauf

Der Live-Test war zunächst nicht fehlerfrei. Er deckte einen Indexstart-Abbruch
unter Windows-cp1252, ein überschrittenes PageIndex-Kontextbudget, verlorene
Schritte bei wiederholten Antwort-Tags und fehlenden Arbeitskontext bei der
Pumpenreinigung auf. Insbesondere konnten Warnungen von Reinigungsschritten
getrennt werden und Transportvorbereitungen in die Antwort gelangen.

Die Korrekturen sind im [Prüfbericht](../AUDIT.md) beschrieben und durch
Regressionstests abgesichert. Vier handbuchspezifische Verfahrensgruppen erhalten
zusammengehörige Warnungen und Arbeitsschritte. Ein relativer Scorefilter reduziert
schwächere Hybrid-Belege. Diese Heuristiken lösen die beobachteten Fälle; sie
beweisen keine allgemeine Sicherheit oder Vollständigkeit der Modellantworten.

## Vorlesen

- In der echten Oberfläche wurde die vollständige Pumpenantwort vorgelesen.
  Das Browserereignis `onstart` löste sichtbar „Vorlesen läuft.“ aus.
- Die Stopptaste brach die Wiedergabe ab und zeigte „Vorlesen gestoppt.“.
- Automatisierte JavaScript-Tests prüfen die abschnittsweise Wiedergabe,
  Abbruch, fehlende Browserunterstützung sowie Text- und Exportfunktionen.
- Die Tonausgabe wurde nicht am Lautsprecher des Nutzers akustisch beurteilt.
  Stimmen und Audioausgabe hängen von Browser und Betriebssystem ab.

## QR-Code und grafische Handy-Anleitung

Die Oberfläche erzeugte einen QR-Code für die vollständige Pumpenantwort.
Der zugehörige HTTPS-Link wurde auf der tatsächlich veröffentlichten
[Leseseite](https://swrobuts.github.io/SiemensWashingMachineTroubleShooting_LocalLLM/)
geöffnet: Alle sieben Einträge einschließlich Sicherheitsmaßnahmen waren
vorhanden. Bei 390 × 844 Pixeln war die Ansicht lesbar; Abhaken wechselte den
Fortschritt von „0 von 7“ auf „1 von 7“. Die Symbole sind Orientierungshilfen,
keine technischen Zeichnungen des konkreten Geräts.

Die Antwort liegt komprimiert im URL-Fragment. Sie wird beim Laden der Seite
nicht als HTTP-Anfrageparameter an GitHub Pages gesendet; sie ist jedoch nicht
verschlüsselt und für jeden mit dem vollständigen Link lesbar. Kein API-Key
gehört zum Exportformat. Die Leseseite braucht keinen Zugang zum lokalen
RAG-Server und erzeugt keine erneute Modellanfrage. Zu große Antworten werden
nicht abgeschnitten; dafür steht ein vollständiger HTML-Export bereit.

Ein physischer Kamerascan und ein akustischer Test auf einem konkreten iPhone
oder Android-Gerät wurden nicht durchgeführt. Die Prüfung umfasst QR-Erstellung,
Link-Rundlauf, veröffentlichte Browserdarstellung, Fortschrittsanzeige und
Schutztests für Darstellung, Größe und Exportdaten.

## Weitere Grenzen

Der LM-Studio-Server auf dem Mac war aus dieser Umgebung nicht erreichbar.
Provider-Routing und OpenAI-kompatibler HTTP-Vertrag wurden automatisiert geprüft;
eine tatsächliche Antwort des Mac-Modells ist damit nicht nachgewiesen.
Die RAG-App bleibt lokal auf Loopback. Öffentlich bereitgestellt wird allein
die statische mobile Leseseite.
