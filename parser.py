from docling.document_converter import DocumentConverter
import time

pdf_file = "siemens-handbuch.pdf"
output_file = "siemens_wissen.md"

print(f"🚀 Starte Docling... Lese '{pdf_file}' ein.")
print("Das kann auf Ihrem Mac einen kurzen Moment dauern, da das PDF visuell analysiert wird...")

start_time = time.time()

# Der KI-gestützte Converter von IBM
converter = DocumentConverter()
result = converter.convert(pdf_file)

# Das Ergebnis als sauberes Markdown speichern
with open(output_file, "w", encoding="utf-8") as f:
    f.write(result.document.export_to_markdown())

end_time = time.time()

print(f"✅ Erfolgreich! Das Handbuch wurde in {round(end_time - start_time, 1)} Sekunden konvertiert.")
print(f"📄 Die strukturierte Datei liegt jetzt hier: {output_file}")