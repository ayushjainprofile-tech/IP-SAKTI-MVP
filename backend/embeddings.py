"""
IP-SAKTI Embedding Utilities

Provides SentenceTransformer-based embeddings for
the TK semantic retrieval pipeline.
"""

from __future__ import annotations

from typing import List, Sequence, Dict, Any, Optional
import os
import math


# =========================================================
# CONFIGURATION
# =========================================================

EMBEDDING_MODEL = os.getenv(
    "IP_SAKTI_EMBEDDING_MODEL",
    "sentence-transformers/all-MiniLM-L6-v2"
)


# =========================================================
# LAZY MODEL
# =========================================================

_model = None


def get_model():
    """
    Load the SentenceTransformer model only when needed.
    """

    global _model

    if _model is None:

        try:
            from sentence_transformers import SentenceTransformer

        except ImportError as exc:

            raise RuntimeError(
                "sentence-transformers is not installed. "
                "Install it using: "
                "pip install sentence-transformers"
            ) from exc

        print(
            f"Loading embedding model: {EMBEDDING_MODEL}"
        )

        _model = SentenceTransformer(
            EMBEDDING_MODEL
        )

        print(
            "Embedding model loaded successfully."
        )

    return _model


# =========================================================
# SINGLE TEXT
# =========================================================

def embed_text(
    text: str
) -> List[float]:
    """
    Generate an embedding for one text string.
    """

    if text is None:
        text = ""

    text = str(text).strip()

    if not text:
        return []

    model = get_model()

    vector = model.encode(
        text,
        normalize_embeddings=True
    )

    return vector.tolist()


# =========================================================
# MULTIPLE TEXTS
# =========================================================

def embed_texts(
    texts: Sequence[str]
) -> List[List[float]]:
    """
    Generate embeddings for multiple texts.
    """

    cleaned = [
        str(text or "").strip()
        for text in texts
    ]

    if not cleaned:
        return []

    model = get_model()

    vectors = model.encode(
        cleaned,
        normalize_embeddings=True
    )

    return vectors.tolist()


# =========================================================
# COSINE SIMILARITY
# =========================================================

def cosine_similarity(
    vector_a: Sequence[float],
    vector_b: Sequence[float]
) -> float:
    """
    Calculate cosine similarity between two vectors.

    Because the SentenceTransformer embeddings are normalized,
    this is effectively their dot product.
    """

    if not vector_a or not vector_b:
        return 0.0

    if len(vector_a) != len(vector_b):
        return 0.0

    dot_product = sum(
        float(a) * float(b)
        for a, b in zip(
            vector_a,
            vector_b
        )
    )

    magnitude_a = math.sqrt(
        sum(
            float(a) * float(a)
            for a in vector_a
        )
    )

    magnitude_b = math.sqrt(
        sum(
            float(b) * float(b)
            for b in vector_b
        )
    )

    if magnitude_a == 0 or magnitude_b == 0:
        return 0.0

    return dot_product / (
        magnitude_a * magnitude_b
    )


# =========================================================
# SEMANTIC SEARCH
# =========================================================

def semantic_search(
    query: str,
    documents: Sequence[Any],
    top_k: int = 5,
    text_key: str = "page_content",
    embedding_key: str = "embedding"
) -> List[Dict[str, Any]]:
    """
    Perform semantic search over documents.

    Each document may be:

        1. A dictionary containing:
           - page_content / text
           - embedding
           - id
           - metadata

        2. An object containing corresponding attributes.

    If embeddings are already stored in the documents,
    they are reused.

    If embeddings are missing, they are generated automatically.
    """

    if not query:
        return []

    if not documents:
        return []

    query_embedding = embed_text(
        query
    )

    if not query_embedding:
        return []

    results = []

    for index, document in enumerate(
        documents
    ):

        # -------------------------------------------------
        # Read document values
        # -------------------------------------------------

        if isinstance(
            document,
            dict
        ):

            text = document.get(
                text_key,
                document.get(
                    "text",
                    ""
                )
            )

            document_embedding = document.get(
                embedding_key
            )

            document_id = document.get(
                "id",
                document.get(
                    "chunk_id",
                    str(index)
                )
            )

            metadata = document.get(
                "metadata",
                {}
            )

        else:

            text = getattr(
                document,
                text_key,
                getattr(
                    document,
                    "text",
                    ""
                )
            )

            document_embedding = getattr(
                document,
                embedding_key,
                None
            )

            document_id = getattr(
                document,
                "id",
                getattr(
                    document,
                    "chunk_id",
                    str(index)
                )
            )

            metadata = getattr(
                document,
                "metadata",
                {}
            )

        # -------------------------------------------------
        # Skip empty documents
        # -------------------------------------------------

        if not text:
            continue

        # -------------------------------------------------
        # Generate document embedding if missing
        # -------------------------------------------------

        if not document_embedding:

            try:

                document_embedding = embed_text(
                    str(text)
                )

            except Exception as exc:

                print(
                    "Embedding error for document:",
                    document_id,
                    repr(exc)
                )

                continue

        # -------------------------------------------------
        # Calculate similarity
        # -------------------------------------------------

        try:

            similarity = cosine_similarity(
                query_embedding,
                document_embedding
            )

            # Numerical safety: cosine similarity should be in [-1, 1].
            # This value is a retrieval signal only; it is never final confidence.
            similarity = max(-1.0, min(1.0, float(similarity)))

        except Exception as exc:

            print(
                "Similarity calculation error:",
                document_id,
                repr(exc)
            )

            continue

        # -------------------------------------------------
        # Build result
        # -------------------------------------------------

        result = {

            "id":
                document_id,

            "similarity":
                round(
                    float(similarity),
                    6
                ),

            # Kept for backward compatibility. This is a semantic-ranking
            # score, NOT a confidence percentage.
            "score":
                round(
                    float(similarity) * 10.0,
                    6
                ),

            "signal_type":
                "semantic_retrieval",

            "confidence_eligible":
                False,

            "page_content":
                str(text),

            "text":
                str(text),

            "metadata":
                metadata
        }

        # -------------------------------------------------
        # Preserve useful document fields
        # -------------------------------------------------

        if isinstance(
            document,
            dict
        ):

            for key in [
                "source",
                "page",
                "chunk",
                "domain"
            ]:

                if key in document:

                    result[key] = document[key]

        results.append(
            result
        )

    # =====================================================
    # SORT BY SEMANTIC SIMILARITY
    # =====================================================

    results.sort(
        key=lambda item: float(
            item.get(
                "similarity",
                0.0
            )
        ),
        reverse=True
    )

    # =====================================================
    # TOP K
    # =====================================================

    return results[
        :max(
            int(top_k),
            1
        )
    ]


# =========================================================
# COMPATIBILITY HELPERS
# =========================================================

def get_embedding(
    text: str
) -> List[float]:
    """
    Compatibility alias used by retrievers.
    """

    return embed_text(
        text
    )


def get_embeddings(
    texts: Sequence[str]
) -> List[List[float]]:
    """
    Compatibility alias for batch embeddings.
    """

    return embed_texts(
        texts
    )


# =========================================================
# TEST
# =========================================================

if __name__ == "__main__":

    print("=" * 60)

    print(
        "IP-SAKTI EMBEDDINGS TEST"
    )

    print("=" * 60)

    sample_text = (
        "Traditional turmeric use for herbal skin care"
    )

    vector = embed_text(
        sample_text
    )

    print(
        "Embedding model:",
        EMBEDDING_MODEL
    )

    print(
        "Embedding dimensions:",
        len(vector)
    )

    print(
        "First 10 values:",
        vector[:10]
    )

    # -----------------------------------------------------
    # Test semantic_search
    # -----------------------------------------------------

    documents = [

        {
            "id":
                "test-1",

            "page_content":
                "Traditional turmeric knowledge "
                "used in herbal medicine."
        },

        {
            "id":
                "test-2",

            "page_content":
                "Patent registration procedure "
                "for inventions."
        }
    ]

    results = semantic_search(
        "traditional turmeric knowledge",
        documents,
        top_k=2
    )

    print(
        "Semantic search results:",
        len(results)
    )

    for result in results:

        print(
            result["id"],
            result["similarity"]
        )

    print("=" * 60)

    print(
        "Embedding test successful."
    )

    print("=" * 60)

# Retrieval similarity is an evidence-ranking signal only.
# It must not be converted directly into final legal/product confidence.
EMBEDDING_ROLE_NOTE = (
    "semantic similarity is retrieval evidence, not final confidence; "
    "final confidence must be computed from the complete product context "
    "and validated evidence"
)
EMBEDDINGS_AVAILABLE = True

# =========================================================
# QUERY EMBEDDING COMPATIBILITY
# =========================================================

def embed_query(text: str) -> List[float]:
    """
    Compatibility helper for the IP-SAKTI RAG retriever.

    The TK retriever expects an embed_query() function.
    Internally we use the same SentenceTransformer
    embedding pipeline as embed_text().
    """
    return embed_text(text)



# =========================================================
# RETRIEVAL-ONLY SEMANTIC SIGNAL
# =========================================================

def semantic_retrieval_signal(similarity: float) -> float:
    """
    Convert cosine similarity into a bounded 0..1 retrieval signal.

    This is for retrieval/context-ranking logic only.
    It must never be presented directly as final confidence.
    """
    try:
        value = float(similarity)
    except (TypeError, ValueError):
        return 0.0

    value = max(-1.0, min(1.0, value))
    return round((value + 1.0) / 2.0, 6)
