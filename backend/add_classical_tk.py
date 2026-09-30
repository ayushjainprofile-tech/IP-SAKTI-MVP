"""Merge curated classical-formulation monographs into data/corpus.json.

Idempotent: existing chunks with the same id are replaced, not duplicated.
Run: python add_classical_tk.py
"""
import json
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CORPUS_PATH = os.path.join(BASE_DIR, "data", "corpus.json")
SOURCE_PATH = os.path.join(BASE_DIR, "data", "tk", "classical_formulations.json")
SOURCE_NAME = "Curated classical formulation monographs (AFI / Samhita summaries)"


def main():
    with open(CORPUS_PATH, "r", encoding="utf-8") as f:
        corpus = json.load(f)
    with open(SOURCE_PATH, "r", encoding="utf-8") as f:
        entries = json.load(f)

    new_ids = {e["id"] for e in entries}
    corpus = [c for c in corpus if c.get("id") not in new_ids]
    for e in entries:
        corpus.append({
            "id": e["id"],
            "domain": "TK",
            "source": SOURCE_NAME,
            "page_content": e["text"],
            "metadata": {
                "filename": "classical_formulations.json",
                "domain": "TK",
                "product": e["product"],
                "extraction_method": "CURATED",
            },
        })

    with open(CORPUS_PATH, "w", encoding="utf-8") as f:
        json.dump(corpus, f, ensure_ascii=False, indent=2)
    print(f"Merged {len(entries)} chunks; corpus now has {len(corpus)} chunks.")


if __name__ == "__main__":
    main()
