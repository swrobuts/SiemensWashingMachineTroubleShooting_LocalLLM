"""Export structured Markdown with actual physical PDF page provenance."""
from pathlib import Path
import argparse

ROOT = Path(__file__).resolve().parent


def convert(pdf_file=ROOT / "siemens-handbuch.pdf", output_file=ROOT / "siemens_wissen.md"):
    from docling.document_converter import DocumentConverter
    result = DocumentConverter().convert(str(pdf_file))
    pages = [f"<!-- pdf-page: {page} -->\n\n" + result.document.export_to_markdown(page_no=page)
             for page in sorted(result.document.pages)]
    target = Path(output_file)
    temporary = target.with_suffix(".md.tmp")
    temporary.write_text("\n\n".join(pages), encoding="utf-8")
    temporary.replace(target)
    print(f"{len(pages)} PDF-Seiten exportiert: {target}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", type=Path, default=ROOT / "siemens-handbuch.pdf")
    ap.add_argument("--output", type=Path, default=ROOT / "siemens_wissen.md")
    args = ap.parse_args()
    convert(args.pdf, args.output)
