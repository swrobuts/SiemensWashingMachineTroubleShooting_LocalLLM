# Eingebundener PageIndex-Code

Ursprung: [VectifyAI/PageIndex](https://github.com/VectifyAI/PageIndex), MIT-Lizenz
(siehe [LICENSE](LICENSE)). Die Kopie war bereits im Ausgangscommit
`a8d9cc4046ed0168561b73879f328e34549a0627` dieses Projekts enthalten.
Der exakte ursprüngliche Upstream-Commit wurde nicht dokumentiert.

Der optionale Baumaufbau nutzt `md_to_tree` und LiteLLM. Das Retrieval der
Web-App steht separat in `pageindex_engine.py` und benutzt den gemeinsamen
OpenAI-kompatiblen Client. Es ist eine vereinfachte Batch-Auswahl, keine
vollständige Implementierung des aktuellen PageIndex SDK.

Änderungen im Audit vom 19.09.2026:

- Veraltete PyPDF2-Imports durch `pypdf as PyPDF2` ersetzt.
- Lokale LiteLLM-Modellkostentabelle als Voreinstellung aktiviert, um beim
  Import keinen spontanen Netzwerkabruf dieser Tabelle auszulösen.
- Lizenzdatei ergänzt.

Updates müssen gegen die tatsächlich verwendete API getestet werden.
Lokaler Betrieb allein ist kein Nachweis einer rechtlichen Datenschutzkonformität.
