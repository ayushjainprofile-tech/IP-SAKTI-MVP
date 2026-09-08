"""
IP-SAKTI Hybrid Corpus Ingestion

Supports:
    1. Normal text PDFs        -> pypdf
    2. Scanned/image PDFs      -> Poppler + Tesseract OCR

Domains:
    backend/data/ip/  -> IP
    backend/data/tk/  -> TK
    backend/data/abs/ -> ABS

Output:
    backend/data/corpus.json
"""

import json
import re
import sys
from pathlib import Path

# ============================================================
# DEPENDENCIES
# ============================================================

try:
    from pypdf import PdfReader
except ImportError:
    print("ERROR: pypdf is missing.")
    print("Run: pip install pypdf")
    sys.exit(1)

try:
    import pytesseract
except ImportError:
    print("ERROR: pytesseract is missing.")
    print("Run: pip install pytesseract")
    sys.exit(1)

try:
    from pdf2image import convert_from_path
except ImportError:
    print("ERROR: pdf2image is missing.")
    print("Run: pip install pdf2image")
    sys.exit(1)


# ============================================================
# PATHS
# ============================================================

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
OUTPUT_PATH = DATA_DIR / "corpus.json"


# ============================================================
# DOMAIN CONFIGURATION
# ============================================================

DOMAIN_FOLDERS = {
    "ip": "IP",
    "tk": "TK",
    "abs": "ABS",
}


# ============================================================
# CHUNK CONFIGURATION
# ============================================================

CHUNK_SIZE = 1200
CHUNK_OVERLAP = 200


# ============================================================
# POPPLER
# ============================================================

# Exact Poppler location found on this machine.
POPPLER_BIN = Path(
    r"C:\Users\Anshika Jain\AppData\Local\Microsoft\WinGet\Packages"
    r"\oschwartz10612.Poppler_Microsoft.Winget.Source_8wekyb3d8bbwe"
    r"\poppler-25.07.0\Library\bin"
)


# ============================================================
# TEXT CLEANING
# ============================================================

def clean_text(text):
    """
    Normalize extracted/OCR text.
    """

    if not text:
        return ""

    text = text.replace("\x00", " ")
    text = text.replace("\n", " ")
    text = text.replace("\r", " ")
    text = re.sub(r"\s+", " ", text)

    return text.strip()


# ============================================================
# NORMAL PDF EXTRACTION
# ============================================================

def extract_text_pdf(pdf_path):
    """
    Extract text from a normal text-based PDF.

    Returns:
        list of (page_number, text)
    """

    pages = []

    try:
        reader = PdfReader(str(pdf_path))
    except Exception as e:
        print(f"  [ERROR] Could not open PDF: {e}")
        return []

    for page_number, page in enumerate(reader.pages, start=1):

        try:
            text = page.extract_text() or ""
        except Exception as e:
            print(
                f"  [WARN] Could not extract "
                f"page {page_number}: {e}"
            )
            text = ""

        text = clean_text(text)

        if text:
            pages.append(
                (page_number, text)
            )

    return pages


# ============================================================
# OCR EXTRACTION
# ============================================================

def extract_ocr_pdf(pdf_path):
    """
    Convert scanned PDF pages to images using Poppler
    and extract text using Tesseract OCR.

    Returns:
        list of (page_number, text)
    """

    pages = []

    print("  [OCR] Starting OCR...")

    if not POPPLER_BIN.exists():
        print(
            f"  [ERROR] Poppler directory not found:\n"
            f"  {POPPLER_BIN}"
        )
        return []

    try:

        images = convert_from_path(
            str(pdf_path),
            dpi=200,
            poppler_path=str(POPPLER_BIN),
            fmt="png",
            thread_count=2,
        )

    except Exception as e:

        print(
            f"  [ERROR] PDF -> image conversion failed: {e}"
        )

        return []

    total_pages = len(images)

    print(
        f"  [OCR] {total_pages} page(s) detected."
    )

    for page_number, image in enumerate(
        images,
        start=1
    ):

        try:

            text = pytesseract.image_to_string(
                image,
                lang="eng",
                config="--psm 6",
            )

        except Exception as e:

            print(
                f"  [WARN] OCR failed on "
                f"page {page_number}: {e}"
            )

            text = ""

        text = clean_text(text)

        if text:

            pages.append(
                (page_number, text)
            )

        print(
            f"    OCR page "
            f"{page_number}/{total_pages}"
        )

    return pages


# ============================================================
# HYBRID PDF EXTRACTION
# ============================================================

def extract_pdf(pdf_path):
    """
    First try normal PDF text extraction.

    If insufficient text is found,
    automatically fall back to OCR.
    """

    print(
        f"  Extracting text: {pdf_path.name}"
    )

    normal_pages = extract_text_pdf(
        pdf_path
    )

    normal_text_length = sum(
        len(text)
        for _, text in normal_pages
    )

    # --------------------------------------------------------
    # Normal PDF
    # --------------------------------------------------------

    if normal_text_length >= 100:

        print(
            f"  [TEXT] Extracted "
            f"{normal_text_length:,} characters."
        )

        return normal_pages, "TEXT"

    # --------------------------------------------------------
    # Scanned PDF
    # --------------------------------------------------------

    print(
        "  [TEXT] Little/no extractable text."
    )

    print(
        "  [FALLBACK] Using OCR..."
    )

    ocr_pages = extract_ocr_pdf(
        pdf_path
    )

    return ocr_pages, "OCR"


# ============================================================
# CHUNKING
# ============================================================

def chunk_text(
    text,
    chunk_size=CHUNK_SIZE,
    overlap=CHUNK_OVERLAP,
):
    """
    Sliding-window chunking.
    """

    if not text:
        return []

    chunks = []

    start = 0
    length = len(text)

    step = max(
        1,
        chunk_size - overlap
    )

    while start < length:

        end = min(
            start + chunk_size,
            length
        )

        chunk = text[
            start:end
        ].strip()

        if chunk:
            chunks.append(
                chunk
            )

        if end >= length:
            break

        start += step

    return chunks


# ============================================================
# FIND PDFs
# ============================================================

def find_pdfs_recursive(folder):
    """
    Recursively find all PDFs.
    """

    if not folder.exists():

        print(
            f"  [MISSING] {folder}"
        )

        return []

    return sorted(
        folder.rglob("*.pdf")
    )


# ============================================================
# BUILD CORPUS
# ============================================================

def build_corpus():

    corpus = []

    summary = {}

    for folder_name, domain in DOMAIN_FOLDERS.items():

        folder = DATA_DIR / folder_name

        pdf_files = find_pdfs_recursive(
            folder
        )

        print()
        print("=" * 70)
        print(
            f"DOMAIN: {domain}"
        )
        print(
            f"FOLDER: {folder}"
        )
        print(
            f"PDF FILES: {len(pdf_files)}"
        )
        print("=" * 70)

        domain_chunks = 0

        for pdf_path in pdf_files:

            print()
            print(
                f"Processing: {pdf_path.name}"
            )

            pages, extraction_method = extract_pdf(
                pdf_path
            )

            if not pages:

                print(
                    "  [SKIP] No text extracted."
                )

                continue

            file_chunks = 0

            for page_number, page_text in pages:

                chunks = chunk_text(
                    page_text
                )

                for chunk_index, chunk in enumerate(
                    chunks
                ):

                    stem = (
                        pdf_path.stem
                        .replace(".pdf", "")
                    )

                    record_id = (
                        f"{domain.lower()}-"
                        f"{stem}-"
                        f"page-{page_number}-"
                        f"chunk-{chunk_index}"
                    )

                    corpus.append(
                        {
                            "id": record_id,

                            "domain": domain,

                            "source": pdf_path.name,

                            "page_content": chunk,

                            "metadata": {
                                "filename": pdf_path.name,
                                "domain": domain,
                                "page": page_number,
                                "chunk": chunk_index,
                                "extraction_method":
                                    extraction_method,
                                "source_path":
                                    str(
                                        pdf_path.relative_to(
                                            BASE_DIR
                                        )
                                    ),
                            },
                        }
                    )

                    file_chunks += 1
                    domain_chunks += 1

            print(
                f"  [{extraction_method}] "
                f"{file_chunks} chunk(s)"
            )

        summary[domain] = {
            "files": len(pdf_files),
            "chunks": domain_chunks,
        }

    return corpus, summary


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print("=" * 70)
    print("IP-SAKTI CORPUS INGESTION")
    print("=" * 70)

    print(
        f"Base directory : {BASE_DIR}"
    )

    print(
        f"Data directory : {DATA_DIR}"
    )

    print(
        f"Output         : {OUTPUT_PATH}"
    )

    print(
        f"Poppler        : {POPPLER_BIN}"
    )

    print("=" * 70)

    if not DATA_DIR.exists():

        print(
            "[ERROR] Data directory does not exist."
        )

        sys.exit(1)

    corpus, summary = build_corpus()

    if not corpus:

        print()
        print(
            "[ERROR] No corpus chunks generated."
        )

        print(
            "Check your PDFs and OCR installation."
        )

        sys.exit(1)

    # --------------------------------------------------------
    # Write corpus
    # --------------------------------------------------------

    with open(
        OUTPUT_PATH,
        "w",
        encoding="utf-8",
    ) as f:

        json.dump(
            corpus,
            f,
            ensure_ascii=False,
            indent=2,
        )

    # --------------------------------------------------------
    # Final summary
    # --------------------------------------------------------

    print()
    print("=" * 70)
    print("INGESTION COMPLETE")
    print("=" * 70)

    for domain, stats in summary.items():

        print(
            f"{domain}: "
            f"{stats['files']} file(s), "
            f"{stats['chunks']} chunk(s)"
        )

    print(
        f"TOTAL CHUNKS: {len(corpus)}"
    )

    print(
        f"OUTPUT: {OUTPUT_PATH}"
    )

    print("=" * 70)


if __name__ == "__main__":
    main()