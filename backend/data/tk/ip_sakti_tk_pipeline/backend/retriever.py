"""
Semantic TK retriever for IP-SAKTI.

Uses the SAME embedding model used during ingestion.
Cosine similarity works because embeddings are normalized.
"""

import json
from pathlib import Path

import numpy as np

from embeddings import embed_query

BASE_DIR = Path(__file__).resolve().parent
INDEX_DIR = BASE_DIR / "data" / "tk_index"

EMBEDDINGS_PATH = INDEX_DIR / "tk_embeddings.npy"
DOCUMENTS_PATH = INDEX_DIR / "tk_documents.json"


class TKRetriever:
    def __init__(self):
        if not EMBEDDINGS_PATH.exists() or not DOCUMENTS_PATH.exists():
            raise FileNotFoundError(
                "TK index not found. Run: python ingest_tk.py"
            )

        self.embeddings = np.load(EMBEDDINGS_PATH)

        self.documents = json.loads(
            DOCUMENTS_PATH.read_text(encoding="utf-8")
        )

        if len(self.embeddings) != len(self.documents):
            raise ValueError(
                "TK embeddings and document count do not match."
            )

    def search(self, query: str, top_k: int = 5, min_score: float = 0.25):
        if not query.strip():
            return []

        query_vector = embed_query(query)

        # Because both sides are normalized, dot product = cosine similarity.
        scores = self.embeddings @ query_vector

        ranked = np.argsort(scores)[::-1]

        results = []

        for idx in ranked:
            score = float(scores[idx])

            if score < min_score:
                continue

            doc = dict(self.documents[int(idx)])
            doc["similarity"] = round(score, 4)

            results.append(doc)

            if len(results) >= top_k:
                break

        return results


_default_retriever = None


def get_tk_retriever():
    global _default_retriever

    if _default_retriever is None:
        _default_retriever = TKRetriever()

    return _default_retriever


def search_tk(query: str, top_k: int = 5, min_score: float = 0.25):
    return get_tk_retriever().search(
        query=query,
        top_k=top_k,
        min_score=min_score,
    )


if __name__ == "__main__":
    import sys

    query = " ".join(sys.argv[1:]).strip()

    if not query:
        query = (
            "Turmeric Ayurvedic traditional knowledge "
            "herbal formulation India"
        )

    print(f"\nQUERY: {query}\n")

    for i, result in enumerate(search_tk(query), start=1):
        print("=" * 70)
        print(f"#{i} similarity={result['similarity']}")
        print(f"Source: {result['source']}")
        print(f"Page: {result.get('page')}")
        print(f"ID: {result['id']}")
        print(result["page_content"][:700])
