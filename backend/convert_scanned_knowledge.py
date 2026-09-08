"""
IP-SAKTI: Convert scanned TK/ABS PDFs to structured JSONL.

Run from backend:
    python convert_scanned_knowledge.py

Requires:
    pymupdf (fitz)
    pytesseract
    pillow
"""

from pathlib import Path
import json
import re
import fitz
import pytesseract
from PIL import Image

BASE = Path(__file__).resolve().parent
DOMAINS = {
    "TK": BASE / "data" / "tk",
    "ABS": BASE / "data" / "abs",
}

def clean(text: str) -> str:
    text = text.replace("\x00", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()

def pdf_has_text(page) -> bool:
    return bool((page.get_text("text") or "").strip())

def convert(domain: str, pdf_path: Path):
    out = pdf_path.with_name(pdf_path.stem + "_structured.jsonl")
    doc = fitz.open(pdf_path)
    records = []

    for page_no, page in enumerate(doc, 1):
        text = clean(page.get_text("text") or "")

        # Scanned page -> OCR only when native extraction is empty.
        if not text:
            pix = page.get_pixmap(matrix=fitz.Matrix(1.35, 1.35), alpha=False)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            text = clean(pytesseract.image_to_string(img, config="--psm 6"))

        if not text:
            print(f"[{domain}] page {page_no}: NO TEXT")
            continue

        # ~1000-character overlapping retrieval chunks.
        start = 0
        chunk_no = 0
        while start < len(text):
            chunk = text[start:start + 1200].strip()
            if chunk:
                chunk_no += 1
                records.append({
                    "id": f"{domain}-{pdf_path.name}-p{page_no}-c{chunk_no}",
                    "domain": domain,
                    "source": pdf_path.name,
                    "page": page_no,
                    "chunk": chunk_no,
                    "retrieval_type": "OCR" if not pdf_has_text(page) else "TEXT",
                    "text": chunk,
                })
            if start + 1200 >= len(text):
                break
            start += 1000

        print(f"[{domain}] page {page_no}/{len(doc)} -> {chunk_no} chunk(s)")

    with out.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"[{domain}] CREATED: {out}")
    print(f"[{domain}] CHUNKS: {len(records)}")
    return out, len(records)

def main():
    print("=" * 70)
    print("IP-SAKTI SCANNED KNOWLEDGE CONVERTER")
    print("=" * 70)

    total = 0
    for domain, folder in DOMAINS.items():
        pdfs = list(folder.glob("*.pdf"))
        if not pdfs:
            print(f"[{domain}] No PDF found in {folder}")
            continue

        for pdf in pdfs:
            _, count = convert(domain, pdf)
            total += count

    print("=" * 70)
    print(f"TOTAL GENERATED CHUNKS: {total}")
    print("=" * 70)

if __name__ == "__main__":
    main()
