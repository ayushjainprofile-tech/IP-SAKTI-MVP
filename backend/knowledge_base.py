"""
IP-SAKTI Knowledge Base

Purpose
-------
Loads and normalizes the project's public/curated knowledge sources so the
retrieval layer receives consistent evidence records.

Supported inputs
----------------
1. JSON / JSONL structured knowledge
2. PDF documents (when PyMuPDF is installed)
3. Existing in-memory records

Design principles
-----------------
- Preserve source, page, domain and other metadata whenever available.
- Never turn retrieval similarity into legal/product confidence.
- Keep evidence traceable to its source document/page/chunk.
- Prefer structured OCR/JSONL over duplicate native PDF text when both exist.
- Keep the module lightweight and compatible with the existing retriever.py.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


# =========================================================
# CONFIGURATION
# =========================================================

BASE_DIR = Path(__file__).resolve().parent

DATA_DIR = BASE_DIR / "data"
CORPUS_PATH = DATA_DIR / "corpus.json"

# Common source folders used by the MVP.
KNOWLEDGE_BASE_DIR = DATA_DIR / "knowledge_base"
DOCUMENTS_DIR = DATA_DIR / "documents"
SOURCES_DIR = DATA_DIR / "sources"
TK_DIR = DATA_DIR / "tk"

DEFAULT_CHUNK_SIZE = int(
    os.getenv("IP_SAKTI_CHUNK_SIZE", "1200")
)

DEFAULT_CHUNK_OVERLAP = int(
    os.getenv("IP_SAKTI_CHUNK_OVERLAP", "180")
)

DEFAULT_MIN_CHUNK_LENGTH = int(
    os.getenv("IP_SAKTI_MIN_CHUNK_LENGTH", "40")
)


# =========================================================
# NORMALIZATION
# =========================================================

def clean(text: Any) -> str:
    """
    Normalize document text without changing its meaning.

    - converts non-breaking spaces
    - removes excessive whitespace
    - preserves punctuation and legal wording
    """
    if text is None:
        return ""

    text = str(text)
    text = text.replace("\x00", " ")
    text = text.replace("\u00a0", " ")
    text = text.replace("\r\n", "\n")
    text = text.replace("\r", "\n")

    # Keep paragraph boundaries, but collapse noisy spaces.
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n[ \t]+", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def normalize_query(text: Any) -> str:
    """
    Normalize a user/retrieval query for deterministic lexical matching.
    """
    text = clean(text).lower()

    replacements = {
        "traditional knowledge": "traditional_knowledge",
        "access and benefit sharing": "access_benefit_sharing",
        "access and benefit-sharing": "access_benefit_sharing",
        "benefit-sharing": "benefit_sharing",
        "biological diversity": "biodiversity",
        "biological resources": "biological_resource",
        "biological resource": "biological_resource",
        "genetic resources": "genetic_resource",
        "genetic resource": "genetic_resource",
        "geographical indications": "geographical_indication",
        "geographical indication": "geographical_indication",
        "aloe-vera": "aloe_vera",
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _tokens(text: Any) -> List[str]:
    normalized = normalize_query(text)
    return re.findall(r"\b[a-z0-9_][a-z0-9_-]*\b", normalized)


# =========================================================
# CHUNKING
# =========================================================

def chunk_text(
    text: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_CHUNK_OVERLAP,
    min_chunk_length: int = DEFAULT_MIN_CHUNK_LENGTH,
) -> List[str]:
    """
    Split text into overlapping chunks.

    The function prefers paragraph/sentence boundaries where possible and
    falls back to character windows for very long legal tables or OCR text.
    """
    text = clean(text)

    if not text:
        return []

    chunk_size = max(int(chunk_size), 200)
    overlap = max(0, min(int(overlap), chunk_size // 2))
    min_chunk_length = max(0, int(min_chunk_length))

    if len(text) <= chunk_size:
        return [text] if len(text) >= min_chunk_length else []

    paragraphs = [
        p.strip()
        for p in re.split(r"\n\s*\n", text)
        if p.strip()
    ]

    chunks: List[str] = []
    current = ""

    def flush() -> None:
        nonlocal current
        value = clean(current)
        if value and len(value) >= min_chunk_length:
            chunks.append(value)
        current = ""

    for paragraph in paragraphs:
        if len(paragraph) <= chunk_size:
            candidate = (
                f"{current}\n\n{paragraph}".strip()
                if current
                else paragraph
            )

            if len(candidate) <= chunk_size:
                current = candidate
                continue

            flush()

            # If the paragraph itself fits, start a new chunk.
            current = paragraph
            continue

        # Very large paragraph: sentence-aware splitting.
        if current:
            flush()

        sentences = re.split(
            r"(?<=[.!?।])\s+",
            paragraph,
        )

        buffer = ""

        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue

            candidate = (
                f"{buffer} {sentence}".strip()
                if buffer
                else sentence
            )

            if len(candidate) <= chunk_size:
                buffer = candidate
                continue

            if buffer:
                chunks.append(buffer)

            # Handle a single sentence larger than the chunk size.
            if len(sentence) > chunk_size:
                start = 0
                while start < len(sentence):
                    end = min(start + chunk_size, len(sentence))
                    piece = sentence[start:end].strip()
                    if len(piece) >= min_chunk_length:
                        chunks.append(piece)
                    if end >= len(sentence):
                        break
                    start = max(end - overlap, start + 1)

                buffer = ""
            else:
                buffer = sentence

        if buffer:
            chunks.append(buffer)

    flush()

    # Add controlled overlap between adjacent chunks.
    if overlap and len(chunks) > 1:
        overlapped: List[str] = [chunks[0]]

        for previous, current_chunk in zip(chunks, chunks[1:]):
            prefix = previous[-overlap:].strip()
            if prefix:
                merged = f"{prefix}\n{current_chunk}".strip()
                if len(merged) > chunk_size:
                    merged = merged[-chunk_size:]
                overlapped.append(merged)
            else:
                overlapped.append(current_chunk)

        chunks = overlapped

    return chunks


# =========================================================
# METADATA
# =========================================================

def _metadata(
    source: str = "",
    page: Optional[int] = None,
    chunk: Optional[int] = None,
    domain: Optional[str] = None,
    **extra: Any,
) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "source": str(source or ""),
        "page": page,
        "chunk": chunk,
    }

    if domain:
        result["domain"] = str(domain).upper()

    for key, value in extra.items():
        if value is not None:
            result[key] = value

    return result


def _infer_domain(
    source: str = "",
    text: str = "",
    explicit_domain: Optional[str] = None,
) -> str:
    """
    Conservative domain inference.

    Explicit metadata always wins. Otherwise use source/text hints.
    UNKNOWN is preferred over making an unsupported legal classification.
    """
    if explicit_domain:
        return str(explicit_domain).upper()

    value = f"{source} {text}".lower()

    if any(
        term in value
        for term in (
            "traditional knowledge",
            "traditional_knowledge",
            "tkdl",
            "ayurveda",
            "indigenous knowledge",
        )
    ):
        return "TK"

    if any(
        term in value
        for term in (
            "access and benefit",
            "access_benefit",
            "biodiversity",
            "biological resource",
            "genetic resource",
            "nagoya",
        )
    ):
        return "ABS"

    if any(
        term in value
        for term in (
            "patent",
            "trademark",
            "copyright",
            "geographical indication",
            "industrial design",
            "intellectual property",
        )
    ):
        return "IP"

    return "UNKNOWN"


# =========================================================
# RECORD CREATION
# =========================================================

def _make_record(
    text: Any,
    *,
    source: str = "",
    page: Optional[int] = None,
    chunk: Optional[int] = None,
    domain: Optional[str] = None,
    record_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    **extra: Any,
) -> Dict[str, Any]:
    value = clean(text)

    if not value:
        return {}

    merged_metadata: Dict[str, Any] = {}

    if isinstance(metadata, dict):
        merged_metadata.update(metadata)

    inferred_domain = _infer_domain(
        source=source,
        text=value,
        explicit_domain=domain or merged_metadata.get("domain"),
    )

    merged_metadata.update(
        _metadata(
            source=source or merged_metadata.get("source", ""),
            page=page if page is not None else merged_metadata.get("page"),
            chunk=chunk if chunk is not None else merged_metadata.get("chunk"),
            domain=inferred_domain,
            **extra,
        )
    )

    source_value = (
        source
        or merged_metadata.get("source")
        or merged_metadata.get("filename")
        or "Unknown source"
    )

    page_value = (
        page
        if page is not None
        else merged_metadata.get("page")
    )

    chunk_value = (
        chunk
        if chunk is not None
        else merged_metadata.get("chunk")
    )

    if record_id:
        identifier = str(record_id)
    else:
        identifier = (
            f"{source_value}|"
            f"{page_value if page_value is not None else 0}|"
            f"{chunk_value if chunk_value is not None else 0}"
        )

    return {
        "id": identifier,
        "page_content": value,
        "text": value,
        "source": str(source_value),
        "page": page_value,
        "chunk": chunk_value,
        "domain": inferred_domain,
        "metadata": merged_metadata,

        # Explicitly communicate that this record is evidence,
        # not a confidence judgment.
        "evidence_record": True,
        "confidence_from_retrieval": False,
    }


# =========================================================
# JSONL
# =========================================================

def load_jsonl(
    path: str | os.PathLike[str],
    *,
    default_domain: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Load a JSONL file.

    Accepted common fields:
    text, page_content, content, source, filename, page, page_number,
    chunk, id, chunk_id, domain, metadata.
    """
    file_path = Path(path)

    if not file_path.exists():
        return []

    records: List[Dict[str, Any]] = []

    with file_path.open("r", encoding="utf-8-sig") as handle:
        for line_number, line in enumerate(handle, start=1):
            line = line.strip()

            if not line:
                continue

            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue

            if isinstance(item, str):
                text = item
                metadata = {}
            elif isinstance(item, dict):
                text = (
                    item.get("page_content")
                    or item.get("text")
                    or item.get("content")
                    or ""
                )
                metadata = item.get("metadata", {})
                if not isinstance(metadata, dict):
                    metadata = {}
            else:
                continue

            if not text:
                continue

            source = (
                item.get("source")
                or item.get("filename")
                or metadata.get("source")
                or metadata.get("filename")
                or file_path.name
            )

            page = (
                item.get("page")
                if item.get("page") is not None
                else item.get("page_number", metadata.get("page"))
            )

            chunk = (
                item.get("chunk")
                if item.get("chunk") is not None
                else metadata.get("chunk")
            )

            domain = (
                item.get("domain")
                or metadata.get("domain")
                or default_domain
            )

            record_id = (
                item.get("id")
                or item.get("chunk_id")
                or metadata.get("id")
                or f"{file_path.name}:{line_number}"
            )

            record = _make_record(
                text,
                source=str(source),
                page=page,
                chunk=chunk,
                domain=domain,
                record_id=str(record_id),
                metadata=metadata,
                source_type="jsonl",
                source_file=str(file_path),
                line_number=line_number,
            )

            if record:
                records.append(record)

    return records


# =========================================================
# JSON
# =========================================================

def load_json(
    path: str | os.PathLike[str],
    *,
    default_domain: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Load a JSON list or a single JSON record."""
    file_path = Path(path)

    if not file_path.exists():
        return []

    try:
        with file_path.open("r", encoding="utf-8-sig") as handle:
            data = json.load(handle)
    except Exception:
        return []

    if isinstance(data, dict):
        # Support wrappers such as {"documents": [...]}
        for key in ("documents", "records", "data", "items", "chunks"):
            if isinstance(data.get(key), list):
                data = data[key]
                break
        else:
            data = [data]

    if not isinstance(data, list):
        return []

    records: List[Dict[str, Any]] = []

    for index, item in enumerate(data):
        if isinstance(item, str):
            text = item
            metadata = {}
        elif isinstance(item, dict):
            text = (
                item.get("page_content")
                or item.get("text")
                or item.get("content")
                or ""
            )
            metadata = item.get("metadata", {})
            if not isinstance(metadata, dict):
                metadata = {}
        else:
            continue

        if not text:
            continue

        source = (
            item.get("source", "")
            if isinstance(item, dict)
            else ""
        ) or metadata.get("source") or file_path.name

        page = (
            item.get("page")
            if isinstance(item, dict)
            and item.get("page") is not None
            else metadata.get("page")
        )

        chunk = (
            item.get("chunk")
            if isinstance(item, dict)
            and item.get("chunk") is not None
            else metadata.get("chunk")
        )

        domain = (
            item.get("domain")
            if isinstance(item, dict)
            else None
        ) or metadata.get("domain") or default_domain

        record_id = (
            item.get("id")
            if isinstance(item, dict)
            else None
        ) or (
            item.get("chunk_id")
            if isinstance(item, dict)
            else None
        ) or f"{file_path.name}:{index}"

        record = _make_record(
            text,
            source=str(source),
            page=page,
            chunk=chunk,
            domain=domain,
            record_id=str(record_id),
            metadata=metadata,
            source_type="json",
            source_file=str(file_path),
        )

        if record:
            records.append(record)

    return records


# =========================================================
# PDF
# =========================================================

def load_pdf(
    path: str | os.PathLike[str],
    *,
    default_domain: Optional[str] = None,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> List[Dict[str, Any]]:
    """
    Load a PDF page-by-page.

    PyMuPDF is intentionally imported lazily so the backend can still start
    when PDF support is not installed.
    """
    file_path = Path(path)

    if not file_path.exists():
        return []

    try:
        import fitz
    except ImportError:
        print(
            "WARNING: PyMuPDF is not installed; "
            f"skipping PDF: {file_path}"
        )
        return []

    records: List[Dict[str, Any]] = []

    try:
        document = fitz.open(str(file_path))
    except Exception as exc:
        print(f"WARNING: Could not open PDF {file_path}: {exc}")
        return []

    try:
        for page_index in range(len(document)):
            page = document[page_index]

            try:
                page_text = page.get_text("text")
            except Exception:
                page_text = ""

            page_text = clean(page_text)

            if not page_text:
                continue

            chunks = chunk_text(
                page_text,
                chunk_size=chunk_size,
                overlap=overlap,
            )

            for chunk_index, chunk in enumerate(chunks):
                record = _make_record(
                    chunk,
                    source=file_path.name,
                    page=page_index + 1,
                    chunk=chunk_index,
                    domain=default_domain,
                    record_id=(
                        f"{file_path.name}:"
                        f"{page_index + 1}:"
                        f"{chunk_index}"
                    ),
                    source_type="pdf",
                    source_file=str(file_path),
                )

                if record:
                    records.append(record)
    finally:
        document.close()

    return records


# =========================================================
# FILE DISCOVERY
# =========================================================

def _candidate_roots(
    roots: Optional[Sequence[str | os.PathLike[str]]] = None,
) -> List[Path]:
    if roots:
        return [Path(root) for root in roots]

    return [
        DATA_DIR,
        KNOWLEDGE_BASE_DIR,
        DOCUMENTS_DIR,
        SOURCES_DIR,
        TK_DIR,
    ]


def _find_files(
    roots: Sequence[Path],
) -> List[Path]:
    found: List[Path] = []
    seen: set[str] = set()

    for root in roots:
        if not root.exists():
            continue

        if root.is_file():
            candidates = [root]
        else:
            candidates = [
                p
                for p in root.rglob("*")
                if p.is_file()
                and p.suffix.lower() in {
                    ".json",
                    ".jsonl",
                    ".pdf",
                }
            ]

        for path in candidates:
            key = str(path.resolve()).lower()

            if key in seen:
                continue

            seen.add(key)
            found.append(path)

    return sorted(found)


# =========================================================
# STRUCTURED / PDF DEDUPLICATION
# =========================================================

def _structured_stem(path: Path) -> str:
    name = path.name.lower()

    for suffix in (
        "_structured.jsonl",
        "_ocr.jsonl",
        ".ocr.jsonl",
        "_text.jsonl",
    ):
        if name.endswith(suffix):
            return name[: -len(suffix)]

    return path.stem.lower()


def _should_skip_pdf(
    pdf_path: Path,
    structured_files: Sequence[Path],
) -> bool:
    """
    If a matching structured/OCR JSONL exists, prefer it over duplicate
    native-PDF ingestion.
    """
    pdf_stem = pdf_path.stem.lower()

    for structured in structured_files:
        stem = _structured_stem(structured)
        if stem == pdf_stem:
            return True

    return False


# =========================================================
# LOAD KNOWLEDGE BASE
# =========================================================

def load_knowledge_base(
    roots: Optional[Sequence[str | os.PathLike[str]]] = None,
    *,
    include_pdfs: bool = True,
    include_json: bool = True,
    include_jsonl: bool = True,
    deduplicate: bool = True,
) -> List[Dict[str, Any]]:
    """
    Discover and load the project's knowledge sources.

    Returns a normalized list of evidence records compatible with
    retriever.py.
    """
    files = _find_files(_candidate_roots(roots))

    jsonl_files = [
        path for path in files
        if path.suffix.lower() == ".jsonl"
    ]

    json_files = [
        path for path in files
        if path.suffix.lower() == ".json"
    ]

    pdf_files = [
        path for path in files
        if path.suffix.lower() == ".pdf"
    ]

    records: List[Dict[str, Any]] = []

    if include_jsonl:
        for path in jsonl_files:
            default_domain = (
                "TK"
                if any(
                    term in path.name.lower()
                    for term in ("tk", "ocr", "traditional")
                )
                else None
            )
            records.extend(
                load_jsonl(
                    path,
                    default_domain=default_domain,
                )
            )

    if include_json:
        for path in json_files:
            # Do not treat the generated corpus itself as another source.
            if path.resolve() == CORPUS_PATH.resolve():
                continue

            records.extend(
                load_json(
                    path,
                    default_domain=None,
                )
            )

    if include_pdfs:
        structured = jsonl_files

        for path in pdf_files:
            if _should_skip_pdf(path, structured):
                continue

            records.extend(
                load_pdf(path)
            )

    if deduplicate:
        records = deduplicate_records(records)

    return records


# =========================================================
# DEDUPLICATION
# =========================================================

def deduplicate_records(
    records: Sequence[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Remove exact/near-exact duplicate evidence while preserving order.
    """
    result: List[Dict[str, Any]] = []
    seen_exact: set[Tuple[str, str, Any, Any]] = set()
    seen_text: set[str] = set()

    for record in records:
        if not isinstance(record, dict):
            continue

        text = clean(
            record.get("page_content")
            or record.get("text")
            or ""
        )

        if not text:
            continue

        source = str(
            record.get("source")
            or record.get("metadata", {}).get("source")
            or ""
        )

        page = record.get(
            "page",
            record.get("metadata", {}).get("page"),
        )

        chunk = record.get(
            "chunk",
            record.get("metadata", {}).get("chunk"),
        )

        exact_key = (
            source.lower(),
            text,
            page,
            chunk,
        )

        normalized_text = normalize_query(text)

        if exact_key in seen_exact:
            continue

        # Only collapse identical normalized text. Do not use fuzzy
        # deduplication because legal wording may differ in meaningful ways.
        if normalized_text in seen_text:
            continue

        seen_exact.add(exact_key)
        seen_text.add(normalized_text)

        result.append(record)

    return result


# =========================================================
# CORPUS PERSISTENCE
# =========================================================

def save_corpus(
    records: Sequence[Dict[str, Any]],
    path: str | os.PathLike[str] = CORPUS_PATH,
) -> str:
    """
    Persist normalized records to corpus.json.
    """
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)

    with output.open("w", encoding="utf-8") as handle:
        json.dump(
            list(records),
            handle,
            ensure_ascii=False,
            indent=2,
        )

    return str(output)


def build_corpus(
    roots: Optional[Sequence[str | os.PathLike[str]]] = None,
    *,
    save: bool = True,
) -> List[Dict[str, Any]]:
    """
    Discover, normalize and optionally persist the knowledge corpus.
    """
    records = load_knowledge_base(roots)

    if save:
        save_corpus(records)

    return records


# =========================================================
# CORPUS LOADING
# =========================================================

def load_corpus(
    path: str | os.PathLike[str] = CORPUS_PATH,
) -> List[Dict[str, Any]]:
    """
    Load the normalized corpus.json if it exists.
    """
    file_path = Path(path)

    if not file_path.exists():
        return []

    try:
        with file_path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except Exception:
        return []

    if not isinstance(data, list):
        return []

    return deduplicate_records(data)


# =========================================================
# RETRIEVAL
# =========================================================

def retrieve(
    query: str,
    records: Optional[Sequence[Dict[str, Any]]] = None,
    *,
    top_k: int = 8,
    domains: Optional[Sequence[str]] = None,
    ingredients: Optional[Sequence[str]] = None,
) -> List[Dict[str, Any]]:
    """
    Lightweight deterministic retrieval.

    This is a fallback/utility retriever. The project's richer retriever.py
    can still perform hybrid semantic + domain + ingredient ranking.

    Scoring:
      - query token overlap
      - requested domain match
      - ingredient match

    Ingredient matches are deliberately capped and are supporting signals
    only. They cannot establish the final legal/product conclusion.
    """
    query_tokens = set(_tokens(query))

    if not query_tokens:
        return []

    if records is None:
        records = load_corpus()

        if not records:
            records = load_knowledge_base()

    requested_domains = {
        str(value).upper()
        for value in (domains or [])
        if str(value).strip()
    }

    ingredient_terms = {
        normalize_query(value)
        for value in (ingredients or [])
        if str(value).strip()
    }

    results: List[Dict[str, Any]] = []

    for record in records:
        if not isinstance(record, dict):
            continue

        text = clean(
            record.get("page_content")
            or record.get("text")
            or ""
        )

        if not text:
            continue

        normalized = normalize_query(text)
        document_tokens = set(_tokens(normalized))

        overlap = len(query_tokens & document_tokens)

        domain = str(
            record.get("domain")
            or record.get("metadata", {}).get("domain")
            or "UNKNOWN"
        ).upper()

        domain_match = bool(
            requested_domains
            and domain in requested_domains
        )

        ingredient_matches = [
            term
            for term in sorted(ingredient_terms)
            if term and term in normalized
        ]

        # Query relevance is the primary signal.
        score = float(overlap)

        if domain_match:
            score += 2.0

        # Supporting ingredient signal is bounded.
        score += min(
            float(len(ingredient_matches)),
            2.0,
        )

        if overlap == 0 and not domain_match and not ingredient_matches:
            continue

        result = dict(record)

        result["score"] = round(score, 4)
        result["similarity"] = None
        result["matched_terms"] = sorted(
            query_tokens & document_tokens
        )
        result["ingredient_matches"] = ingredient_matches
        result["domain_match"] = domain_match
        result["retrieval_type"] = "knowledge_base"
        result["retrieval_similarity_is_not_confidence"] = True
        result["ingredient_evidence_is_supporting_only"] = bool(
            ingredient_matches
        )

        results.append(result)

    results.sort(
        key=lambda item: (
            float(item.get("score", 0.0)),
            bool(item.get("domain_match")),
            len(item.get("matched_terms", [])),
            len(item.get("ingredient_matches", [])),
        ),
        reverse=True,
    )

    return results[:max(1, int(top_k))]


# =========================================================
# STATS
# =========================================================

def stats(
    records: Optional[Sequence[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Return corpus statistics for debugging/UI.
    """
    if records is None:
        records = load_corpus()

    records = list(records)

    domain_counts: Dict[str, int] = {}
    source_counts: Dict[str, int] = {}

    total_chars = 0

    for record in records:
        if not isinstance(record, dict):
            continue

        domain = str(
            record.get("domain")
            or record.get("metadata", {}).get("domain")
            or "UNKNOWN"
        ).upper()

        source = str(
            record.get("source")
            or record.get("metadata", {}).get("source")
            or "Unknown source"
        )

        domain_counts[domain] = domain_counts.get(domain, 0) + 1
        source_counts[source] = source_counts.get(source, 0) + 1

        total_chars += len(
            str(
                record.get("page_content")
                or record.get("text")
                or ""
            )
        )

    return {
        "documents": len(records),
        "domains": domain_counts,
        "sources": source_counts,
        "total_characters": total_chars,
        "average_chunk_length": (
            round(total_chars / len(records), 2)
            if records
            else 0.0
        ),
        "corpus_path": str(CORPUS_PATH),
    }


# =========================================================
# DEBUG / CLI
# =========================================================

if __name__ == "__main__":
    print("=" * 70)
    print("IP-SAKTI KNOWLEDGE BASE")
    print("=" * 70)

    records = load_corpus()

    if not records:
        print("No corpus.json found; discovering source files...")
        records = load_knowledge_base()

    information = stats(records)

    print("Records:", information["documents"])
    print("Domains:", information["domains"])
    print("Sources:", len(information["sources"]))
    print("Average chunk length:", information["average_chunk_length"])

    if records:
        print("\nSample record:")
        sample = records[0]
        print("ID:", sample.get("id"))
        print("Source:", sample.get("source"))
        print("Page:", sample.get("page"))
        print("Domain:", sample.get("domain"))
        print("Text:", sample.get("page_content", "")[:500])

    print("=" * 70)
