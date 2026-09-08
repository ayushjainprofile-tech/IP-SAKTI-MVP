"""
IP-SAKTI TK ingestion pipeline with OCR fallback.

Pipeline:

    TK PDF
      ↓
    PyMuPDF text extraction
      ↓
    If no text → Tesseract OCR
      ↓
    Clean text
      ↓
    Chunk text
      ↓
    BAAI/bge-small-en-v1.5 embeddings
      ↓
    tk_index/
        tk_documents.json
        tk_embeddings.npy
        manifest.json
"""

import json
import re
from pathlib import Path

import numpy as np
import fitz  # PyMuPDF
import pytesseract
from PIL import Image

from embeddings import embed_documents


# ============================================================
# PATHS
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

SOURCE_DIR = BASE_DIR / "data" / "tk_sources"
CORPUS_PATH = BASE_DIR / "data" / "corpus.json"
INDEX_DIR = BASE_DIR / "data" / "tk_index"


# ============================================================
# CHUNK SETTINGS
# ============================================================

CHUNK_SIZE = 900
CHUNK_OVERLAP = 150
MIN_CHUNK_LENGTH = 80


# ============================================================
# EMBEDDING MODEL
# ============================================================

EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"


# ============================================================
# TEXT CLEANING
# ============================================================

def clean_text(text: str) -> str:
    """
    Normalize extracted/OCR text.
    """

    if not text:
        return ""

    text = text.replace("\x00", " ")

    # Remove excessive whitespace
    text = re.sub(r"\s+", " ", text)

    return text.strip()


# ============================================================
# CHUNKING
# ============================================================

def chunk_text(text: str):
    """
    Split text into overlapping chunks.
    """

    text = clean_text(text)

    if not text:
        return []

    chunks = []

    start = 0

    while start < len(text):

        end = min(start + CHUNK_SIZE, len(text))

        chunk = text[start:end].strip()

        if len(chunk) >= MIN_CHUNK_LENGTH:
            chunks.append(chunk)

        if end >= len(text):
            break

        start = max(
            end - CHUNK_OVERLAP,
            start + 1
        )

    return chunks


# ============================================================
# OCR
# ============================================================

def ocr_page(page):
    """
    Convert a PDF page to an image and run Tesseract OCR.
    """

    print("      Running OCR...")

    # Render page at 200 DPI
    matrix = fitz.Matrix(200 / 72, 200 / 72)

    pix = page.get_pixmap(
        matrix=matrix,
        alpha=False
    )

    image = Image.frombytes(
        "RGB",
        [pix.width, pix.height],
        pix.samples
    )

    text = pytesseract.image_to_string(
        image,
        config="--psm 6"
    )

    return clean_text(text)


# ============================================================
# PDF INGESTION
# ============================================================

def ingest_pdfs():

    documents = []

    pdf_files = sorted(
        SOURCE_DIR.glob("*.pdf")
    )

    if not pdf_files:

        print()
        print("No PDF files found.")
        print(f"Expected folder:")
        print(SOURCE_DIR)

        return documents

    for pdf_path in pdf_files:

        print()
        print("=" * 70)
        print(f"Reading PDF: {pdf_path.name}")
        print("=" * 70)

        try:

            reader = fitz.open(
                str(pdf_path)
            )

        except Exception as exc:

            print(
                f"ERROR opening {pdf_path.name}: {exc}"
            )

            continue

        print(
            f"Pages found: {len(reader)}"
        )

        for page_index in range(len(reader)):

            page_number = page_index + 1

            page = reader[page_index]

            print(
                f"\n  Page {page_number}/{len(reader)}"
            )

            # ------------------------------------------------
            # First attempt: normal PDF text extraction
            # ------------------------------------------------

            text = clean_text(
                page.get_text("text")
            )

            if text:

                print(
                    f"      Extracted text: {len(text)} characters"
                )

            # ------------------------------------------------
            # Second attempt: OCR
            # ------------------------------------------------

            if len(text) < MIN_CHUNK_LENGTH:

                print(
                    "      Little/no text detected."
                )

                text = ocr_page(page)

                if text:

                    print(
                        f"      OCR extracted: {len(text)} characters"
                    )

                else:

                    print(
                        "      OCR returned no text."
                    )

            # ------------------------------------------------
            # Create chunks
            # ------------------------------------------------

            chunks = chunk_text(text)

            print(
                f"      Chunks created: {len(chunks)}"
            )

            for chunk_number, chunk in enumerate(
                chunks,
                start=1
            ):

                documents.append(
                    {
                        "id": (
                            f"tk-"
                            f"{pdf_path.stem}-"
                            f"{page_number}-"
                            f"{chunk_number}"
                        ),

                        "domain": "TK",

                        "source": pdf_path.name,

                        "page": page_number,

                        "chunk": chunk_number,

                        "page_content": chunk,
                    }
                )

        reader.close()

    return documents


# ============================================================
# EXISTING CORPUS SUPPORT
# ============================================================

def ingest_existing_tk_corpus():

    if not CORPUS_PATH.exists():

        print(
            f"\nNo corpus found at: {CORPUS_PATH}"
        )

        return []

    try:

        data = json.loads(
            CORPUS_PATH.read_text(
                encoding="utf-8"
            )
        )

    except Exception as exc:

        print(
            f"Could not read corpus.json: {exc}"
        )

        return []

    if not isinstance(data, list):

        print(
            "corpus.json is not a list."
        )

        return []

    documents = []

    for item in data:

        if not isinstance(item, dict):
            continue

        if (
            str(
                item.get("domain", "")
            ).upper()
            != "TK"
        ):
            continue

        text = clean_text(
            item.get(
                "page_content",
                ""
            )
        )

        if not text:
            continue

        metadata = (
            item.get("metadata")
            or {}
        )

        documents.append(
            {
                "id": (
                    item.get("id")
                    or f"tk-corpus-{len(documents)}"
                ),

                "domain": "TK",

                "source": (
                    item.get("source")
                    or metadata.get("filename")
                    or "corpus.json"
                ),

                "page": metadata.get("page"),

                "chunk": metadata.get("chunk"),

                "page_content": text,
            }
        )

    print(
        f"TK records found in corpus.json: {len(documents)}"
    )

    return documents


# ============================================================
# DEDUPLICATION
# ============================================================

def deduplicate(documents):

    seen = set()

    result = []

    for doc in documents:

        key = (
            doc["source"],
            doc.get("page"),
            doc["page_content"],
        )

        if key in seen:
            continue

        seen.add(key)

        result.append(doc)

    return result


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print("=" * 70)
    print("IP-SAKTI TK INGESTION PIPELINE")
    print("=" * 70)

    print()
    print(f"Source directory:")
    print(SOURCE_DIR)

    print()
    print(f"Index directory:")
    print(INDEX_DIR)

    # Make sure directories exist
    SOURCE_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    INDEX_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    # --------------------------------------------------------
    # Collect documents
    # --------------------------------------------------------

    documents = []

    # Existing TK records
    documents.extend(
        ingest_existing_tk_corpus()
    )

    # PDF records
    pdf_documents = ingest_pdfs()

    documents.extend(
        pdf_documents
    )

    # Deduplicate
    documents = deduplicate(
        documents
    )

    print()
    print("=" * 70)
    print(
        f"TOTAL TK DOCUMENT CHUNKS: {len(documents)}"
    )
    print("=" * 70)

    # --------------------------------------------------------
    # No documents
    # --------------------------------------------------------

    if not documents:

        print()
        print("NO TK DOCUMENTS FOUND.")
        print()
        print(
            "Put authorized/public TK PDFs in:"
        )
        print(SOURCE_DIR)

        print()
        print(
            "Or add TK records to:"
        )
        print(CORPUS_PATH)

        return 1

    # --------------------------------------------------------
    # Show sample
    # --------------------------------------------------------

    print()
    print("Sample extracted text:")
    print("-" * 70)

    print(
        documents[0]["page_content"][:500]
    )

    print("-" * 70)

    # --------------------------------------------------------
    # Generate embeddings
    # --------------------------------------------------------

    texts = [
        doc["page_content"]
        for doc in documents
    ]

    print()
    print(
        f"Creating embeddings for {len(texts)} TK chunks..."
    )

    embeddings = embed_documents(
        texts
    ).astype("float32")

    print()
    print(
        f"Embedding shape: {embeddings.shape}"
    )

    # --------------------------------------------------------
    # Save embeddings
    # --------------------------------------------------------

    embeddings_path = (
        INDEX_DIR
        / "tk_embeddings.npy"
    )

    np.save(
        embeddings_path,
        embeddings
    )

    # --------------------------------------------------------
    # Save documents
    # --------------------------------------------------------

    documents_path = (
        INDEX_DIR
        / "tk_documents.json"
    )

    documents_path.write_text(
        json.dumps(
            documents,
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )

    # --------------------------------------------------------
    # Save manifest
    # --------------------------------------------------------

    manifest = {

        "embedding_model":
            EMBEDDING_MODEL,

        "document_count":
            len(documents),

        "embedding_dimension":
            int(embeddings.shape[1]),

        "domain":
            "TK",

        "ocr_enabled":
            True,

        "chunk_size":
            CHUNK_SIZE,

        "chunk_overlap":
            CHUNK_OVERLAP,
    }

    manifest_path = (
        INDEX_DIR
        / "manifest.json"
    )

    manifest_path.write_text(
        json.dumps(
            manifest,
            indent=2
        ),
        encoding="utf-8"
    )

    # --------------------------------------------------------
    # Finished
    # --------------------------------------------------------

    print()
    print("=" * 70)
    print("TK INGESTION COMPLETE")
    print("=" * 70)

    print()
    print(
        f"Documents : {len(documents)}"
    )

    print(
        f"Embeddings: {embeddings.shape}"
    )

    print(
        f"Index     : {INDEX_DIR}"
    )

    print()
    print("Created files:")

    print(
        f"  {embeddings_path}"
    )

    print(
        f"  {documents_path}"
    )

    print(
        f"  {manifest_path}"
    )

    print()

    return 0


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    raise SystemExit(
        main()
    )