const fs = require("fs");
const path = require("path");
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  ImageRun, AlignmentType, LevelFormat, HeadingLevel, BorderStyle,
  WidthType, ShadingType, TableOfContents, PageBreak,
} = require("docx");

const DIA = path.join(__dirname, "diagrams");
const NAVY = "000028", CYAN = "00AAB4", INK = "22242E";

// PNG-Größe aus dem Header lesen (Breite/Höhe, Big-Endian ab Byte 16)
function pngSize(file) {
  const b = fs.readFileSync(file);
  return { w: b.readUInt32BE(16), h: b.readUInt32BE(20) };
}

// Bild volle Breite (max ~630 px) mit korrektem Seitenverhältnis + Bildunterschrift
function figure(name, caption) {
  const p = path.join(DIA, name);
  const { w, h } = pngSize(p);
  const width = 630, height = Math.round(width * h / w);
  return [
    new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { before: 160, after: 40 },
      children: [new ImageRun({
        type: "png", data: fs.readFileSync(p),
        transformation: { width, height },
        altText: { title: caption, description: caption, name },
      })],
    }),
    new Paragraph({
      alignment: AlignmentType.CENTER, spacing: { after: 200 },
      children: [new TextRun({ text: caption, italics: true, size: 18, color: "666666" })],
    }),
  ];
}

const H1 = (t) => new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun(t)] });
const H2 = (t) => new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun(t)] });
const P = (runs) => new Paragraph({
  spacing: { after: 120 }, alignment: AlignmentType.JUSTIFIED,
  children: Array.isArray(runs) ? runs : [new TextRun(runs)],
});
const B = (t) => new Paragraph({
  numbering: { reference: "bullets", level: 0 }, spacing: { after: 60 },
  children: Array.isArray(t) ? t : [new TextRun(t)],
});
const bold = (t) => new TextRun({ text: t, bold: true });
const txt = (t) => new TextRun(t);
const code = (t) => new TextRun({ text: t, font: "Consolas", size: 20, color: "0A3D62" });

// Tabelle aus 2D-Array (erste Zeile = Kopf)
function table(rows, widths) {
  const total = widths.reduce((a, b) => a + b, 0);
  const border = { style: BorderStyle.SINGLE, size: 1, color: "CCCCCC" };
  const borders = { top: border, bottom: border, left: border, right: border };
  return new Table({
    width: { size: total, type: WidthType.DXA }, columnWidths: widths,
    rows: rows.map((cells, r) => new TableRow({
      tableHeader: r === 0,
      children: cells.map((c, i) => new TableCell({
        borders, width: { size: widths[i], type: WidthType.DXA },
        shading: { fill: r === 0 ? "D5E8F0" : "FFFFFF", type: ShadingType.CLEAR },
        margins: { top: 60, bottom: 60, left: 120, right: 120 },
        children: [new Paragraph({ children: [new TextRun({ text: c, bold: r === 0, size: 19 })] })],
      })),
    })),
  });
}

const children = [];

// ── Titelblock ──
children.push(
  new Paragraph({ spacing: { before: 1200, after: 0 }, alignment: AlignmentType.CENTER,
    children: [new TextRun({ text: "Technische Dokumentation", bold: true, size: 56, color: NAVY })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 60 },
    children: [new TextRun({ text: "Lokaler Siemens-Waschmaschinen-Troubleshooting-Assistent", size: 30, color: CYAN, bold: true })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 40 },
    children: [new TextRun({ text: "RAG-Pipeline · Dokumentenaufbereitung · Retrieval · Antwortgenerierung", size: 22, color: "666666" })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 600 },
    children: [new TextRun({ text: "Stand: 09.07.2026", size: 20, color: "999999" })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 200 },
    children: [new TextRun({ text: "Vollständig lokal (DSGVO-konform) · keine Cloud · mit Quellenangabe und Halluzinationsschutz", italics: true, size: 20, color: INK })] }),
  new Paragraph({ children: [new PageBreak()] }),
);

// ── Inhaltsverzeichnis ──
children.push(
  new Paragraph({ spacing: { after: 160 }, children: [new TextRun({ text: "Inhaltsverzeichnis", bold: true, size: 30, color: NAVY })] }),
  new TableOfContents("Inhalt", { hyperlink: true, headingStyleRange: "1-2" }),
  new Paragraph({ children: [new PageBreak()] }),
);

// ── 1. Überblick ──
children.push(H1("1. Überblick"));
children.push(P([
  txt("Das System beantwortet Fragen zu einer Siemens-Waschmaschine ausschließlich aus dem offiziellen Handbuch — "),
  bold("vollständig lokal"), txt(" (das lokale Sprachmodell läuft in LM Studio, die Vektorsuche und Embeddings ebenfalls; keine Daten verlassen den Rechner). Jede Antwort nennt ihre "),
  bold("Quelle (Abschnitt + Seite)"), txt(" und ein "), bold("Guardrail"),
  txt(" verhindert erfundene Antworten bei fachfremden Fragen."),
]));
children.push(P([
  txt("Die Verarbeitung besteht aus zwei Phasen: der "), bold("Offline-Aufbereitung"),
  txt(" (das PDF-Handbuch wird einmalig in einen durchsuchbaren Vektorindex überführt) und der "),
  bold("Online-Abfrage"), txt(" (pro Nutzerfrage wird der passende Handbuch-Kontext gesucht und beantwortet)."),
]));
children.push(...figure("d1_architektur.png", "Abbildung 1: Gesamtarchitektur — Offline-Aufbereitung und Online-Abfrage."));

// ── 2. Dokumentenaufbereitung ──
children.push(H1("2. Dokumentenaufbereitung"));
children.push(P([
  txt("Dies ist der qualitätsentscheidende Teil. Ein RAG-System kann nur so gut antworten, wie der abgerufene Kontext gut ist. Jeder der folgenden Schritte wurde per Retrieval-Evaluation messbar begründet (siehe Kapitel 6)."),
]));
children.push(...figure("d2_aufbereitung.png", "Abbildung 2: Die Offline-Pipeline im Überblick — von PDF bis persistentem Vektorindex."));

children.push(H2("2.1 Schritt 1 — PDF-Extraktion mit Docling"));
children.push(P([
  txt("Das Handbuch ist ein visuell gesetztes PDF (mehrspaltig, mit Tabellen, Symbolen und Warnhinweisen). Naive Text-Extraktion zerreißt Lesereihenfolge und Tabellen. Stattdessen analysiert "),
  bold("Docling"), txt(" (IBM) das Layout KI-gestützt — Lesereihenfolge, Tabellenstruktur, OCR — und liefert "),
  bold("strukturiertes Markdown"), txt(" ("), code("siemens_wissen.md"), txt("). Markdown ist verlustarm strukturiert, für Menschen prüfbar und strukturbewusst chunkbar."),
]));

children.push(H2("2.2 Schritt 2 — Struktur der Wissensbasis"));
children.push(P([txt("Die Wissensbasis umfasst rund 1.900 Zeilen mit 187 Abschnitten ("), code("##"), txt(") und ~190 Tabellenzeilen. Zwei Besonderheiten prägen das Chunking:")]));
children.push(B([bold("Die Kronjuwelen sind Tabellen. "), txt("Fehlercodes und Störungen stehen in zwei großen Tabellen („Hinweise im Anzeigefeld“, „Störungen, was tun?“).")]));
children.push(B([bold("OCR-Artefakte. "), txt("Manche Docling-Überschriften sind verrauscht; sie stören kaum, weil die Antworten im Tabellen-/Fließtext stehen.")]));

children.push(H2("2.3 Schritt 3 — Chunking: der entscheidende Schritt"));
children.push(P([txt("Das Dokument wird in zwei Stufen in durchsuchbare „Chunks“ (Nodes) zerlegt:")]));
children.push(B([bold("Struktur-Chunking: "), txt("Der MarkdownNodeParser schneidet an den "), code("##"), txt("-Überschriften.")]));
children.push(B([bold("Tabellen-Explosion (entscheidend): "), txt("Die Fehlercode-Tabelle landet sonst als "), bold("ein"), txt(" ~6.400-Zeichen-Block und embeddet als semantischer „Brei“ — eine konkrete Frage wie „Fehler E:18“ findet ihn dann nicht (empirisch: nicht unter den Top-60 Vektortreffern). Große tabellenlastige Nodes werden deshalb "), bold("pro Zeile"), txt(" aufgeteilt und als lesbarer Fließtext gerendert.")]));
children.push(...figure("d3_tabellen.png", "Abbildung 3: Tabellen-Explosion — aus einem unauffindbaren Block werden pro Fehlercode auffindbare Chunks."));

children.push(H2("2.4 Schritt 4 — Lokale Embeddings mit korrekten Präfixen"));
children.push(P([
  txt("Jeder Chunk wird lokal in einen Vektor überführt ("), code("intfloat/multilingual-e5-small"),
  txt("). Wichtig: e5-Modelle sind "), bold("asymmetrisch"), txt(" trainiert und verlangen Präfixe — Fragen als "),
  code("query:"), txt(", Textstücke als "), code("passage:"),
  txt(". Ohne diese Präfixe sinkt die Trefferqualität deutlich (das war der größte stille Fehler der Ausgangsversion)."),
]));

children.push(H2("2.5 Schritt 5 — Vektorindex mit Persistenz"));
children.push(P([
  txt("Die Vektoren wandern in einen Vektorindex, der nach "), code("storage/"), txt(" persistiert wird — sonst würde jeder Serverstart alles neu embedden. Ein "),
  bold("Cache-Schlüssel"), txt(" aus Quelldatei-Inhalt, Embedding-Modell und Parser-Version stellt sicher, dass ein veralteter Index nie fälschlich geladen wird: Ändert sich eines davon, wird automatisch neu gebaut."),
]));

// ── 3. Retrieval ──
children.push(new Paragraph({ children: [new PageBreak()] }));
children.push(H1("3. Retrieval-Pipeline (online)"));
children.push(H2("3.1 Hybrides Retrieval"));
children.push(P([
  txt("Pro Frage kombiniert das System zwei Signale: eine "), bold("Vektorsuche"),
  txt(" (semantische Ähnlichkeit, Top-12) und einen "), bold("exakten Fehlercode-Lookup"),
  txt(". Dense-Embeddings sind bei seltenen Tokens wie „E:18“ prinzipiell schwach — enthält die Frage einen Fehlercode, wird der Chunk mit genau diesem Code garantiert ins Kandidatenset gelegt."),
]));
children.push(...figure("d5_hybrid.png", "Abbildung 4: Hybrides Retrieval — Vektorsuche plus garantierter Fehlercode-Lookup."));

children.push(H2("3.2 Reranking und Gesamtfluss"));
children.push(P([
  txt("Die ~12 Kandidaten werden von einem "), bold("Cross-Encoder"), txt(" ("), code("BAAI/bge-reranker-v2-m3"),
  txt(") neu bewertet. Er liest Frage und Chunk gemeinsam und ist dadurch weit präziser als reine Vektorähnlichkeit; er reduziert auf die relevantesten "), bold("Top-5"), txt(" — genau das, was das Sprachmodell als Kontext sieht."),
]));
children.push(...figure("d4_pipeline.png", "Abbildung 5: Abfrage-Pipeline — das Guardrail entscheidet vor dem Sprachmodell."));

// ── 4. Guardrail ──
children.push(H1("4. Guardrail — Schutz vor Halluzination"));
children.push(P([
  txt("Der Reranker liefert Relevanz-Scores zwischen 0 und 1. Kalibriert auf der Zielmaschine: fachlich passende Fragen scoren "), bold("≥ 0,435"), txt(", fachfremde "), bold("≈ 0,000"),
  txt(". Liegt der beste Score unter der Schwelle "), code("0.15"), txt(", wird "), bold("ohne Sprachmodell-Aufruf"),
  txt(" mit „das steht nicht im Handbuch“ geantwortet. Als zweite Schicht weist der Prompt das Modell an, bei fehlender Information ehrlich zu sein."),
]));
children.push(...figure("d6_guardrail.png", "Abbildung 6: Guardrail — kalibrierte Score-Schwelle trennt In- und Out-of-Scope."));

// ── 5. Antwort/Streaming ──
children.push(H1("5. Antwortgenerierung und Streaming"));
children.push(P([
  txt("Die Top-5-Chunks bilden den Kontext eines Prompts, den ein lokales Modell in LM Studio beantwortet (Standard: "),
  code("gemma-4-12b-it-mlx"), txt(", ein schnelles Nicht-Reasoning-Modell). Der Prompt erzwingt eine "),
  bold("strukturierte Ausgabe"), txt(" (Zusammenfassung, Handbuch-Schritte, Tipps), die in Karten und Checklisten übersetzt wird. Die "),
  bold("Quellenangabe"), txt(" wird aus den tatsächlich genutzten Chunks abgeleitet („Handbuch: <Abschnitt> · Seite NN“)."),
]));
children.push(P([
  txt("Die Antwort wird per "), bold("Server-Sent Events (SSE)"), txt(" gestreamt: Der Nutzer sieht die Quelle nach ~1 Sekunde und die Antwort beim Entstehen — statt minutenlang auf einen Spinner zu warten. Da der eingebaute Streaming-Pfad der RAG-Bibliothek puffert, wird das Sprachmodell direkt gestreamt."),
]));
children.push(...figure("d7_streaming.png", "Abbildung 7: Streaming-Ablauf — Quelle sofort, Antwort Token für Token."));

// ── 6. Evaluation ──
children.push(new Paragraph({ children: [new PageBreak()] }));
children.push(H1("6. Ergebnisse (Evaluation)"));
children.push(P([
  txt("Ein Eval-Skript misst die "), bold("Retrieval-Qualität ohne Sprachmodell"),
  txt(" an 10 realen Störungsfragen, deren erwartete Stichwörter aus den echten Handbuch-Tabellen stammen. Verglichen wird die Ausgangsversion mit der optimierten Version (auf der Zielmaschine gemessen):"),
]));
children.push(...figure("d8_eval.png", "Abbildung 8: Retrieval-Qualität vorher/nachher."));
children.push(table([
  ["Metrik", "Bedeutung", "Original", "Final"],
  ["hit@1", "Oberster Chunk ist der richtige", "40 %", "100 %"],
  ["Recall", "Anteil relevanter Fakten im Kontext", "33 %", "96 %"],
  ["MRR", "Mittlerer Rang des Treffers", "0,52", "1,00"],
  ["Out-of-Scope", "Fachfremde Fragen abgefangen", "0 / 6", "6 / 6"],
], [1900, 4260, 1600, 1600]));
children.push(new Paragraph({ spacing: { before: 120 }, children: [new TextRun({
  text: "Interpretation: Vorher war in 60 % der Fälle der oberste Abschnitt nicht der richtige; nur ein Drittel der relevanten Fakten war im Kontext. Nachher trifft jede Frage den richtigen Abschnitt zuoberst.",
  italics: true, size: 20, color: "555555" })] }));

// ── 7. Konfiguration ──
children.push(H1("7. Konfiguration"));
children.push(P("Das Verhalten lässt sich über Umgebungsvariablen steuern (Auswahl):"));
children.push(table([
  ["Variable", "Default", "Zweck"],
  ["LOCAL_LLM_MODEL", "gemma-4-12b-it-mlx", "Modell in LM Studio"],
  ["EMBED_MODEL", "multilingual-e5-small", "lokales Embedding (Index rebuildet bei Wechsel)"],
  ["RERANK_MODEL", "bge-reranker-v2-m3", "Cross-Encoder-Reranker"],
  ["RETRIEVE_K / FINAL_K", "12 / 5", "Overfetch bzw. finale Chunks"],
  ["GUARDRAIL_MIN_SCORE", "0.15", "Mindest-Score; darunter „nicht im Handbuch“"],
], [3000, 2600, 3760]));

// ── 8. Betrieb ──
children.push(H1("8. Betrieb"));
children.push(B([code("python3 parser.py"), txt("  — PDF → siemens_wissen.md (nur bei neuem Handbuch)")]));
children.push(B([code("python3 server.py"), txt("  — Web-API auf Port 3001, dann index.html öffnen")]));
children.push(B([code("python3 lokale_ki.py \"Fehler E:23?\""), txt("  — Terminal-CLI")]));
children.push(B([code("python3 eval/run_eval.py"), txt("  — Retrieval-Qualität messen (ohne Sprachmodell)")]));
children.push(new Paragraph({ spacing: { before: 160 }, children: [new TextRun({
  text: "Die Dokumentenverarbeitung (Kapitel 2) ist zusätzlich als eigenständiges Google-Colab-Notebook verfügbar: notebooks/document_processing_pipeline.ipynb.",
  italics: true, size: 20, color: "555555" })] }));

// ── Dokument ──
const doc = new Document({
  styles: {
    default: { document: { run: { font: "Arial", size: 22 } } },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 32, bold: true, font: "Arial", color: NAVY },
        paragraph: { spacing: { before: 320, after: 160 }, outlineLevel: 0 } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 26, bold: true, font: "Arial", color: "0A3D62" },
        paragraph: { spacing: { before: 220, after: 100 }, outlineLevel: 1 } },
    ],
  },
  numbering: { config: [
    { reference: "bullets", levels: [{ level: 0, format: LevelFormat.BULLET, text: "•",
      alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 560, hanging: 280 } } } }] },
  ] },
  sections: [{
    properties: { page: {
      size: { width: 12240, height: 15840 },
      margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 },
    } },
    children,
  }],
});

const OUT = "/Users/robert/Library/CloudStorage/OneDrive-Persönlich/Vorlesungen/Datenbasierte Fallstudien/SiemensWashingMachineTroubleShooting_LocalLLM/docs/Technische_Dokumentation.docx";
Packer.toBuffer(doc).then((buf) => { fs.writeFileSync(OUT, buf); console.log("geschrieben:", OUT, buf.length, "bytes"); });
