from pathlib import Path
from pypdf import PdfReader
import json
import re

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
OUTPUT_FILE = DATA_DIR / "corpus.json"

DOMAIN_MAP = {
    "ip": "IP",
    "tk": "TK",
    "abs": "ABS",
}


def clean_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def chunk_text(text: str, chunk_size: int = 1200, overlap: int = 200):
    chunks = []

    start = 0

    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end].strip()

        if chunk:
            chunks.append(chunk)

        start += chunk_size - overlap

    return chunks


def process_pdf(pdf_path: Path, domain: str):
    print(f"Processing: {pdf_path.name}")

    reader = PdfReader(str(pdf_path))

    full_text = ""

    for page_number, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
            full_text += f"\n{text}"
        except Exception as e:
            print(f"Could not read page {page_number}: {e}")

    full_text = clean_text(full_text)

    chunks = chunk_text(full_text)

    records = []

    for i, chunk in enumerate(chunks):
        records.append({
            "id": f"{domain.lower()}-{pdf_path.stem}-{i}",
            "domain": domain,
            "source": pdf_path.name,
            "page_content": chunk,
            "metadata": {
                "filename": pdf_path.name,
                "domain": domain,
                "chunk": i
            }
        })

    print(f"  Extracted {len(chunks)} chunks")

    return records


def main():
    all_records = []

    for folder_name, domain in DOMAIN_MAP.items():

        folder = DATA_DIR / folder_name

        if not folder.exists():
            print(f"Skipping missing folder: {folder}")
            continue

        for pdf_file in folder.glob("*.pdf"):
            records = process_pdf(pdf_file, domain)
            all_records.extend(records)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(all_records, f, ensure_ascii=False, indent=2)

    print()
    print("=" * 50)
    print(f"Corpus created: {OUTPUT_FILE}")
    print(f"Total chunks: {len(all_records)}")
    print("=" * 50)


if __name__ == "__main__":
    main()