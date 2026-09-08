"""
IP-SAKTI Knowledge Base
Loads native-text PDFs plus structured OCR JSONL for TK/ABS.
"""

from pathlib import Path
import json
import re
from typing import Dict, Any, List

try:
    import fitz
except ImportError:
    fitz = None

BASE = Path(__file__).resolve().parent
DATA = BASE / "data"

DOMAIN_DIRS = {
    "IP": DATA / "ip",
    "TK": DATA / "tk",
    "ABS": DATA / "abs",
}

def clean(text: str) -> str:
    text = text.replace("\x00", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()

def chunk_text(text: str, size: int = 1200, overlap: int = 200):
    text = clean(text)
    if not text:
        return []
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        part = text[start:end].strip()
        if part:
            chunks.append(part)
        if end >= len(text):
            break
        start = end - overlap
    return chunks

def load_jsonl(domain: str, path: Path) -> List[Dict[str, Any]]:
    rows = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            row["domain"] = domain
            row["text"] = clean(str(row.get("text", "")))
            if row["text"]:
                rows.append(row)
    except Exception as e:
        print(f"[KB] Failed JSONL {path.name}: {e}")
    return rows

def load_pdf(domain: str, path: Path) -> List[Dict[str, Any]]:
    if fitz is None:
        return []

    rows = []
    try:
        doc = fitz.open(path)
        for page_no, page in enumerate(doc, 1):
            text = clean(page.get_text("text") or "")
            if not text:
                continue

            for chunk_no, chunk in enumerate(chunk_text(text), 1):
                rows.append({
                    "id": f"{domain}-{path.name}-p{page_no}-c{chunk_no}",
                    "domain": domain,
                    "source": path.name,
                    "page": page_no,
                    "chunk": chunk_no,
                    "retrieval_type": "TEXT",
                    "text": chunk,
                })
    except Exception as e:
        print(f"[KB] Failed PDF {path.name}: {e}")
    return rows

def load_knowledge_base() -> List[Dict[str, Any]]:
    all_rows = []

    for domain, folder in DOMAIN_DIRS.items():
        folder.mkdir(parents=True, exist_ok=True)

        # Structured OCR files take priority.
        jsonls = list(folder.glob("*_structured.jsonl"))
        for path in jsonls:
            rows = load_jsonl(domain, path)
            all_rows.extend(rows)
            print(f"[KB] Loaded {domain}: {path.name} ({len(rows)} chunks)")

        # Native PDF text is loaded too.
        for path in folder.glob("*.pdf"):
            # Avoid duplicate ingestion if structured OCR exists for this PDF.
            structured = path.with_name(path.stem + "_structured.jsonl")
            if structured.exists():
                continue

            rows = load_pdf(domain, path)
            all_rows.extend(rows)
            print(f"[KB] Loaded {domain}: {path.name} ({len(rows)} chunks)")

    return all_rows

def normalize_query(query: str) -> List[str]:
    return [
        x.lower()
        for x in re.findall(r"[a-zA-Z0-9][a-zA-Z0-9_-]+", query)
        if len(x) > 2
    ]

def retrieve(query: str, domain: str = None, top_k: int = 5):
    rows = load_knowledge_base()
    terms = set(normalize_query(query))
    scored = []

    for row in rows:
        if domain and row["domain"].upper() != domain.upper():
            continue

        text = row["text"].lower()
        matched = [t for t in terms if t in text]
        if not matched:
            continue

        # Simple deterministic lexical score.
        score = sum(text.count(t) for t in matched) + 0.25 * len(matched)

        scored.append({
            **row,
            "score": round(score, 4),
            "matched_terms": matched,
        })

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:top_k]

def stats():
    rows = load_knowledge_base()
    result = {
        "total_chunks": len(rows),
        "domains": {}
    }

    for domain in DOMAIN_DIRS:
        domain_rows = [r for r in rows if r["domain"] == domain]
        result["domains"][domain] = {
            "chunks": len(domain_rows),
            "sources": len(set(r["source"] for r in domain_rows)),
        }

    return result

if __name__ == "__main__":
    print("=" * 70)
    print("IP-SAKTI KNOWLEDGE BASE TEST")
    print("=" * 70)

    s = stats()
    print(json.dumps(s, indent=2))

    query = (
        "Herbal Skin Care Cream turmeric aloe vera "
        "Traditional herbal skin care cosmetic India "
        "traditional knowledge biodiversity access benefit sharing "
        "intellectual property patent trademark"
    )

    for domain in ("IP", "TK", "ABS"):
        print(f"\n========== {domain} ==========")
        results = retrieve(query, domain=domain, top_k=3)

        if not results:
            print("NO EVIDENCE FOUND")
            continue

        for r in results:
            print(
                f"\nScore: {r['score']}\n"
                f"Source: {r['source']}\n"
                f"Page: {r.get('page')}\n"
                f"Chunk: {r.get('chunk')}\n"
                f"Matched: {r['matched_terms']}\n"
                f"Text: {r['text'][:700]}"
            )
