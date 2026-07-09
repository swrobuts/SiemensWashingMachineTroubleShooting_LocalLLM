# -*- coding: utf-8 -*-
"""Erzeugt die Diagramme (PNG) für die Word-Dokumentation."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Polygon
from pathlib import Path

OUT = Path(__file__).parent / "diagrams"
OUT.mkdir(exist_ok=True)

NAVY = "#000028"; CYAN = "#00AAB4"; GRAY = "#ECEEF1"; INK = "#22242E"
GREEN = "#2E9E5B"; RED = "#C0392B"; AMBER = "#D98A0B"; WHITE = "#FFFFFF"
plt.rcParams["font.family"] = "DejaVu Sans"


def new(w=12, h=6.5):
    fig, ax = plt.subplots(figsize=(w, h))
    ax.set_xlim(0, 100); ax.set_ylim(0, 100); ax.axis("off")
    return fig, ax


def box(ax, cx, cy, w, h, text, fc=GRAY, tc=INK, fs=11, bold=False, ec=NAVY, lw=1.2, round=True):
    style = "round,pad=0.3,rounding_size=1.6" if round else "square,pad=0.3"
    ax.add_patch(FancyBboxPatch((cx - w / 2, cy - h / 2), w, h, boxstyle=style,
                                fc=fc, ec=ec, lw=lw, zorder=2))
    ax.text(cx, cy, text, ha="center", va="center", fontsize=fs, color=tc,
            fontweight="bold" if bold else "normal", zorder=3, wrap=True)


def diamond(ax, cx, cy, w, h, text, fc=AMBER, tc=WHITE, fs=10):
    pts = [(cx, cy + h / 2), (cx + w / 2, cy), (cx, cy - h / 2), (cx - w / 2, cy)]
    ax.add_patch(Polygon(pts, closed=True, fc=fc, ec=NAVY, lw=1.2, zorder=2))
    ax.text(cx, cy, text, ha="center", va="center", fontsize=fs, color=tc, fontweight="bold", zorder=3)


def arrow(ax, x1, y1, x2, y2, color=NAVY, style="-|>", lw=1.8, ls="-", rad=0.0):
    ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle=style, mutation_scale=16,
                                 color=color, lw=lw, linestyle=ls,
                                 connectionstyle=f"arc3,rad={rad}", zorder=1))


def caption(ax, cx, cy, text, fs=8.5, color="#555"):
    ax.text(cx, cy, text, ha="center", va="center", fontsize=fs, color=color, style="italic")


def title(ax, text):
    ax.text(50, 97, text, ha="center", va="top", fontsize=15, color=NAVY, fontweight="bold")


def save(fig, name):
    fig.savefig(OUT / name, dpi=200, bbox_inches="tight", facecolor="white", pad_inches=0.15)
    plt.close(fig)
    print("✔", name)


# ── D1: Gesamtarchitektur ───────────────────────────────────────────────────
def d1():
    fig, ax = new(12, 6.8)
    title(ax, "Gesamtarchitektur — zwei Phasen")
    ax.text(50, 90, "OFFLINE (einmalig)", ha="center", fontsize=12, color=CYAN, fontweight="bold")
    off = ["siemens-\nhandbuch.pdf", "Docling", "siemens_\nwissen.md", "Chunking", "e5-\nEmbeddings", "Vektorindex\n(storage/)"]
    xs = [8.5, 24.5, 41, 57, 74, 91]
    for i, (x, t) in enumerate(zip(xs, off)):
        fc = NAVY if i in (0, 5) else GRAY
        tc = WHITE if i in (0, 5) else INK
        box(ax, x, 78, 14, 12, t, fc=fc, tc=tc, bold=True, fs=10)
        if i < 5: arrow(ax, x + 7, 78, xs[i + 1] - 7, 78)
    ax.text(50, 46, "ONLINE (pro Frage)", ha="center", fontsize=12, color=CYAN, fontweight="bold")
    on = ["Nutzer-\nfrage", "Hybrid-\nRetrieval", "Cross-Encoder\nReranking", "Guardrail", "Lokales LLM\n(LM Studio)", "Antwort\n(+ Quelle)"]
    for i, (x, t) in enumerate(zip(xs, on)):
        fc = NAVY if i in (0, 5) else GRAY
        tc = WHITE if i in (0, 5) else INK
        box(ax, x, 33, 14, 12, t, fc=fc, tc=tc, bold=True, fs=10)
        if i < 5: arrow(ax, x + 7, 33, xs[i + 1] - 7, 33)
    arrow(ax, 91, 72, 24.5, 39, color=CYAN, ls="--", lw=1.6, rad=-0.15)
    ax.text(58, 58, "persistenter Index speist das Retrieval", ha="center", fontsize=9, color=CYAN, style="italic")
    ax.text(8.5, 14, "Antwort wird live gestreamt (SSE): Quelle < 1 s, dann Token für Token",
            ha="left", fontsize=8.5, color="#555", style="italic")
    save(fig, "d1_architektur.png")


# ── D2: Dokumentenaufbereitung (Detail) ─────────────────────────────────────
def d2():
    fig, ax = new(13, 6.2)
    title(ax, "Dokumentenaufbereitung — Schritt für Schritt (offline)")
    steps = [
        ("PDF", "siemens-\nhandbuch.pdf", "visuell gesetzt:\nSpalten, Tabellen"),
        ("① Docling", "PDF → Markdown", "Layout, Lese-\nreihenfolge, OCR"),
        ("siemens_wissen.md", "187 ##-Abschnitte\n~190 Tab.-Zeilen", "prüfbar,\nstrukturiert"),
        ("② Chunking", "MarkdownNodeParser\n+ Tabellen-Explosion", "Fehlercode je\nZeile auffindbar"),
        ("③ Embeddings", "e5, query:/passage:", "lokal,\nDSGVO"),
        ("④ Vektorindex", "+ Persistenz\n(Hash-Invalidierung)", "kein Neu-\nEmbedding"),
    ]
    xs = [8.5, 25.4, 42.3, 59.2, 76.1, 92.0]
    bw = 14.0
    for i, (x, (head, mid, cap)) in enumerate(zip(xs, steps)):
        fc = NAVY if i in (0, 2) else (CYAN if head.startswith(("①", "②", "③", "④")) else GRAY)
        tc = WHITE if fc in (NAVY, CYAN) else INK
        ax.text(x, 78, head, ha="center", fontsize=9, color=NAVY, fontweight="bold")
        box(ax, x, 66, bw, 15, mid, fc=fc, tc=tc, fs=8.5)
        caption(ax, x, 50, cap)
        if i < 5: arrow(ax, x + bw / 2, 66, xs[i + 1] - bw / 2, 66)
    # Hervorhebung Tabellen-Explosion
    ax.text(50, 30, "Kernschritt: große Tabellen werden PRO ZEILE gechunkt —\nsonst wird z. B. „Fehler E:18\" im 6.400-Zeichen-Block nicht gefunden.",
            ha="center", fontsize=10, color=RED, fontweight="bold")
    save(fig, "d2_aufbereitung.png")


# ── D3: Tabellen-Explosion vorher/nachher ───────────────────────────────────
def d3():
    fig, ax = new(12, 6.6)
    title(ax, "Chunking-Kernidee: Tabellen-Explosion (vorher / nachher)")
    ax.text(25, 88, "VORHER", ha="center", fontsize=12, color=RED, fontweight="bold")
    box(ax, 25, 72, 34, 16, "Fehlercode-Tabelle\n≈ 6.400 Zeichen  =  1 Node\n(E:18, E:23, … alles zusammen)", fc=GRAY, fs=10)
    arrow(ax, 25, 64, 25, 52, color=RED)
    box(ax, 25, 44, 30, 12, "Frage „Fehler E:18\"\n→ NICHT gefunden", fc=RED, tc=WHITE, bold=True, fs=10)
    ax.text(75, 88, "NACHHER", ha="center", fontsize=12, color=GREEN, fontweight="bold")
    ys = [78, 71, 64]
    labels = ["E:18 | Laugenpumpe verstopft …", "E:23 | Bodenwanne, Undichtigkeit …", "…  (je Zeile ein Chunk)"]
    for y, t in zip(ys, labels):
        box(ax, 75, y, 34, 5.6, t, fc="#EAF7F1", ec=GREEN, fs=9)
    arrow(ax, 75, 60.5, 75, 52, color=GREEN)
    box(ax, 75, 44, 30, 12, "Frage „Fehler E:18\"\n→ Treffer auf Rang 1", fc=GREEN, tc=WHITE, bold=True, fs=10)
    arrow(ax, 43, 72, 57, 72, color=NAVY, lw=2.2)
    ax.text(50, 76, "Explosion", ha="center", fontsize=9.5, color=NAVY, fontweight="bold")
    ax.text(50, 28, "Zusätzlich werden Zellen als lesbarer Fließtext gerendert (statt gepaddter Rohzeile),\ndamit nicht Ausrichtungs-Whitespace das Embedding dominiert.",
            ha="center", fontsize=9.5, color="#555", style="italic")
    save(fig, "d3_tabellen.png")


# ── D4: Online-Abfrage-Pipeline mit Guardrail ───────────────────────────────
def d4():
    fig, ax = new(12, 6.2)
    title(ax, "Abfrage-Pipeline (online)")
    box(ax, 10, 60, 15, 12, "Nutzer-\nfrage", fc=NAVY, tc=WHITE, bold=True)
    box(ax, 30, 60, 16, 12, "Hybrid-\nRetrieval", fc=GRAY)
    box(ax, 50, 60, 16, 12, "Cross-Encoder\nReranking", fc=GRAY)
    diamond(ax, 70, 60, 16, 20, "Score\n≥ 0.15?")
    box(ax, 89, 74, 18, 12, "LLM (LM Studio)\n→ Streaming", fc=CYAN, tc=WHITE, bold=True)
    box(ax, 89, 42, 18, 12, "„nicht im\nHandbuch\"", fc=RED, tc=WHITE, bold=True)
    for x1, x2 in [(17.5, 22), (38, 42), (58, 62)]:
        arrow(ax, x1, 60, x2, 60)
    arrow(ax, 74, 66, 80, 74); ax.text(78, 72, "ja", fontsize=9, color=GREEN, fontweight="bold")
    arrow(ax, 74, 54, 80, 42); ax.text(78, 49, "nein", fontsize=9, color=RED, fontweight="bold")
    box(ax, 89, 92, 20, 8, "Antwort + Quellenangabe (Seite NN)", fc="#EAF7F1", ec=GREEN, fs=9)
    arrow(ax, 89, 80, 89, 88, color=GREEN)
    ax.text(50, 26, "Guardrail entscheidet VOR dem LLM — fachfremde Fragen kosten keinen Modell-Aufruf.",
            ha="center", fontsize=9.5, color="#555", style="italic")
    save(fig, "d4_pipeline.png")


# ── D5: Hybrid-Retrieval ────────────────────────────────────────────────────
def d5():
    fig, ax = new(12, 6.2)
    title(ax, "Hybrides Retrieval — Vektor + exakter Fehlercode-Lookup")
    box(ax, 12, 60, 15, 12, "Nutzer-\nfrage", fc=NAVY, tc=WHITE, bold=True)
    box(ax, 40, 78, 26, 12, "Vektorsuche (e5)\nTop-12 semantisch", fc=GRAY)
    box(ax, 40, 42, 26, 12, "Fehlercode-Lookup\n„E:18\" exakt", fc=GRAY)
    box(ax, 68, 60, 16, 12, "Kandidaten\n(vereint)", fc=CYAN, tc=WHITE, bold=True)
    box(ax, 89, 60, 16, 12, "Reranking\n→ Top-5", fc=NAVY, tc=WHITE, bold=True)
    arrow(ax, 19.5, 62, 27, 76, rad=0.1); arrow(ax, 19.5, 58, 27, 44, rad=-0.1)
    arrow(ax, 53, 76, 60, 63, rad=-0.1); arrow(ax, 53, 44, 60, 57, rad=0.1)
    arrow(ax, 76, 60, 81, 60)
    ax.text(50, 24, "Warum? Dense-Embeddings finden seltene Codes wie „E:18\" schlecht —\nder exakte Lookup garantiert den richtigen Chunk im Kandidatenset.",
            ha="center", fontsize=9.5, color="#555", style="italic")
    save(fig, "d5_hybrid.png")


# ── D6: Guardrail-Kalibrierung ──────────────────────────────────────────────
def d6():
    fig, ax = new(11, 6.2)
    title(ax, "Guardrail — kalibriert am Reranker-Score")
    # Skala
    ax.plot([15, 85], [55, 55], color="#999", lw=2, zorder=1)
    for v, lab in [(15, "0.0"), (50, "0.15"), (85, "1.0")]:
        ax.plot([v, v], [53, 57], color="#999", lw=1.5)
        ax.text(v, 50, lab, ha="center", fontsize=9, color="#555")
    ax.axvline(50, ymin=0.25, ymax=0.75, color=NAVY, ls="--", lw=1.5)
    ax.text(50, 66, "Schwelle 0.15", ha="center", fontsize=9.5, color=NAVY, fontweight="bold")
    ax.text(27, 72, "Out-of-Scope\n≈ 0.000", ha="center", fontsize=10, color=RED, fontweight="bold")
    ax.text(70, 72, "In-Scope\n≥ 0.435", ha="center", fontsize=10, color=GREEN, fontweight="bold")
    box(ax, 27, 34, 30, 12, "„nicht im Handbuch\"\n(kein LLM-Aufruf)", fc=RED, tc=WHITE, bold=True, fs=10)
    box(ax, 70, 34, 30, 12, "Antwort aus Handbuch\n(+ Quelle)", fc=GREEN, tc=WHITE, bold=True, fs=10)
    arrow(ax, 40, 52, 30, 41, color=RED); arrow(ax, 60, 52, 68, 41, color=GREEN)
    ax.text(50, 16, "Gemessen: 6/6 fachfremde Fragen abgefangen, 0 In-Scope-Fragen fälschlich blockiert.",
            ha="center", fontsize=9.5, color="#555", style="italic")
    save(fig, "d6_guardrail.png")


# ── D7: Streaming-Sequenz (SSE) ─────────────────────────────────────────────
def d7():
    fig, ax = new(11, 7)
    title(ax, "Streaming-Ablauf (Server-Sent Events)")
    for x, lab in [(25, "Browser (index.html)"), (75, "Server (/api/ask_stream)")]:
        ax.text(x, 88, lab, ha="center", fontsize=11, color=NAVY, fontweight="bold")
        ax.plot([x, x], [12, 84], color="#BBB", lw=1.5, ls="--", zorder=0)
    def msg(y, x1, x2, text, color=NAVY, t=""):
        arrow(ax, x1, y, x2, y, color=color)
        ax.text((x1 + x2) / 2, y + 2.5, text, ha="center", fontsize=9, color=color)
        if t: ax.text(x2 + 1 if x2 > x1 else x2 - 1, y, t, ha="left" if x2 > x1 else "right",
                      va="center", fontsize=8, color="#777")
    msg(78, 25, 75, "POST Frage")
    ax.text(75, 70, "Retrieval + Rerank + Guardrail", ha="center", fontsize=8.5, color="#777", style="italic")
    msg(64, 75, 25, "event: meta  (Quelle)", color=CYAN, t="≈ 1 s")
    ax.add_patch(FancyBboxPatch((60, 44), 30, 10, boxstyle="round,pad=0.3", fc="#F4FAFB", ec=CYAN, lw=1))
    ax.text(75, 49, "LLM streamt Token\nfür Token", ha="center", fontsize=8.5, color=CYAN)
    for y in (40, 35, 30):
        msg(y, 75, 25, "event: token", color=CYAN)
    ax.text(10, 35, "Live-Vorschau\nwächst", ha="center", va="center", fontsize=8, color="#777")
    msg(22, 75, 25, "event: result  (strukturierte Karten)", color=GREEN)
    ax.text(50, 8, "Nutzer sieht die Quelle sofort und die Antwort beim Entstehen — statt Minuten-Spinner.",
            ha="center", fontsize=9.5, color="#555", style="italic")
    save(fig, "d7_streaming.png")


# ── D8: Eval vorher/nachher ─────────────────────────────────────────────────
def d8():
    fig, ax = plt.subplots(figsize=(9, 5.2))
    metrics = ["hit@1", "Recall", "MRR (×100)"]
    orig = [40, 33, 52]; final = [100, 96, 100]
    import numpy as np
    x = np.arange(len(metrics)); w = 0.38
    b1 = ax.bar(x - w / 2, orig, w, label="Original", color="#B9C0C9")
    b2 = ax.bar(x + w / 2, final, w, label="Final", color=CYAN)
    for b in list(b1) + list(b2):
        ax.text(b.get_x() + b.get_width() / 2, b.get_height() + 1.5, f"{int(b.get_height())}%",
                ha="center", fontsize=10, fontweight="bold", color=INK)
    ax.set_ylim(0, 112); ax.set_ylabel("Prozent", fontsize=11)
    ax.set_xticks(x); ax.set_xticklabels(metrics, fontsize=11)
    ax.set_title("Retrieval-Qualität: vorher vs. nachher (10 reale Störungsfragen)",
                 fontsize=13, color=NAVY, fontweight="bold", pad=12)
    ax.legend(fontsize=11, frameon=False, loc="upper left")
    ax.spines[["top", "right"]].set_visible(False)
    fig.savefig(OUT / "d8_eval.png", dpi=200, bbox_inches="tight", facecolor="white", pad_inches=0.15)
    plt.close(fig); print("✔ d8_eval.png")


for f in (d1, d2, d3, d4, d5, d6, d7, d8):
    f()
print("\nAlle Diagramme in", OUT)
