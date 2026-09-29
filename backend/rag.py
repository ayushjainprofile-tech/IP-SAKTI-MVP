import json
import os
import re
from typing import List, Dict, Any

import numpy as np

from embeddings import embed_query



# =========================================================
# CONTEXT-AWARE RAG QUERY
# =========================================================

def build_context_aware_query(product) -> str:
    """Build one query from the complete product context.

    Retrieval similarity is evidence-ranking only; it is NOT final
    confidence. All available product fields are included so that
    ingredient matches cannot dominate the query by themselves.
    """
    parts = []

    for field in (
        "product_name",
        "purpose",
        "product_type",
        "jurisdiction",
    ):
        value = getattr(product, field, "")
        if value:
            parts.append(str(value))

    ingredients = getattr(product, "ingredients", []) or []
    if ingredients:
        parts.append("ingredients: " + ", ".join(map(str, ingredients)))

    tk = getattr(product, "based_on_traditional_knowledge", "")
    if tk:
        parts.append("traditional knowledge: " + str(tk))

    return " | ".join(parts)


# =========================================================
# CONFIG
# =========================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

CORPUS_PATH = os.path.join(
    BASE_DIR,
    "data",
    "corpus.json"
)

TK_INDEX_DIR = os.path.join(
    BASE_DIR,
    "data",
    "tk_index"
)

TK_EMBEDDINGS_PATH = os.path.join(
    TK_INDEX_DIR,
    "tk_embeddings.npy"
)

TK_DOCUMENTS_PATH = os.path.join(
    TK_INDEX_DIR,
    "tk_documents.json"
)


# =========================================================
# INGREDIENT ALIASES
# =========================================================

INGREDIENT_ALIASES = {

    "turmeric": {
        "turmeric",
        "curcuma",
        "curcuma_longa",
        "curcumin"
    },

    "aloe": {
        "aloe",
        "aloe_vera",
        "aloe_barbadensis",
        "barbadensis"
    }
}


# =========================================================
# DOMAIN CONCEPTS
# =========================================================

DOMAIN_CONCEPTS = {

    "TK": {
        "traditional knowledge",
        "traditional_knowledge",
        "traditional use",
        "traditional_use",
        "ayurveda",
        "ayurvedic",
        "indigenous knowledge",
        "indigenous",
        "folk knowledge",
        "herbal knowledge"
    },

    "ABS": {
        "access and benefit sharing",
        "access_benefit_sharing",
        "benefit sharing",
        "benefit_sharing",
        "biological resource",
        "biological_resource",
        "biological resources",
        "biodiversity",
        "genetic resource",
        "genetic_resource"
    },

    "IP": {
        "patent",
        "invention",
        "trademark",
        "copyright",
        "industrial design",
        "geographical indication",
        "geographical_indication"
    }
}


# =========================================================
# NORMALIZATION
# =========================================================

def normalize_text(text: Any) -> str:

    if text is None:
        return ""

    text = str(text).lower()

    replacements = {

        "traditional knowledge":
            "traditional_knowledge",

        "access and benefit sharing":
            "access_benefit_sharing",

        "access and benefit-sharing":
            "access_benefit_sharing",

        "benefit-sharing":
            "benefit_sharing",

        "biological diversity":
            "biodiversity",

        "bio-diversity":
            "biodiversity",

        "biological resources":
            "biological_resource",

        "biological resource":
            "biological_resource",

        "genetic resources":
            "genetic_resource",

        "genetic resource":
            "genetic_resource",

        "geographical indications":
            "geographical_indication",

        "geographical indication":
            "geographical_indication",

        "aloe-vera":
            "aloe_vera",
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    text = re.sub(
        r"[^a-z0-9_\s-]",
        " ",
        text
    )

    text = re.sub(
        r"\s+",
        " ",
        text
    )

    return text.strip()


# =========================================================
# TOKENIZATION
# =========================================================

def tokenize(text: str) -> set:

    normalized = normalize_text(text)

    return set(
        re.findall(
            r"\b[a-z][a-z0-9_]{2,}\b",
            normalized
        )
    )


# =========================================================
# INGREDIENT CANONICALIZATION
# =========================================================

def canonical_ingredient(
    ingredient: str
) -> str:

    normalized = normalize_text(
        ingredient
    )

    for canonical, aliases in INGREDIENT_ALIASES.items():

        if normalized == canonical:
            return canonical

        if normalized in aliases:
            return canonical

        for alias in aliases:

            if alias in normalized.split():
                return canonical

            if alias in normalized:
                return canonical

    return normalized


# =========================================================
# GET INGREDIENT ALIASES
# =========================================================

def get_ingredient_aliases(
    ingredient: str
) -> set:

    canonical = canonical_ingredient(
        ingredient
    )

    aliases = INGREDIENT_ALIASES.get(
        canonical,
        {canonical}
    )

    return set(aliases)


# =========================================================
# FIND INGREDIENT MATCHES
# =========================================================

def find_ingredient_matches(
    ingredient_list: List[str],
    document_text: str
) -> List[str]:

    normalized_document = normalize_text(
        document_text
    )

    matches = set()

    for ingredient in ingredient_list:

        aliases = get_ingredient_aliases(
            ingredient
        )

        for alias in aliases:

            normalized_alias = normalize_text(
                alias
            )

            if not normalized_alias:
                continue

            pattern = (
                r"(?<![a-z0-9_])"
                + re.escape(normalized_alias)
                + r"(?![a-z0-9_])"
            )

            if re.search(
                pattern,
                normalized_document
            ):

                matches.add(
                    normalized_alias
                )

    return sorted(matches)


# =========================================================
# FIND DOMAIN CONCEPTS
# =========================================================

def find_domain_concepts(
    domains: List[str],
    document_text: str
) -> Dict[str, List[str]]:

    normalized_document = normalize_text(
        document_text
    )

    found = {}

    for domain in domains:

        domain = str(domain).upper()

        concepts_found = []

        for concept in DOMAIN_CONCEPTS.get(
            domain,
            set()
        ):

            normalized_concept = normalize_text(
                concept
            )

            if normalized_concept in normalized_document:

                concepts_found.append(
                    normalized_concept
                )

        found[domain] = sorted(
            set(concepts_found)
        )

    return found




# =========================================================
# CONTEXT ALIGNMENT HELPERS
# =========================================================

def _context_tokens(text: Any) -> set:
    return tokenize(str(text or ""))


def _alignment_score(reference: Any, evidence_text: Any) -> float:
    """Measure lexical/context alignment; never uses retrieval similarity."""
    ref_tokens = _context_tokens(reference)
    ev_tokens = _context_tokens(evidence_text)
    if not ref_tokens or not ev_tokens:
        return 0.0
    overlap = len(ref_tokens & ev_tokens) / max(1, len(ref_tokens))
    return round(min(1.0, overlap), 4)


def _purpose_alignment(product, evidence_text: str) -> float:
    purpose = getattr(product, "purpose", "")
    return _alignment_score(purpose, evidence_text)


def _product_type_alignment(product, evidence_text: str) -> float:
    product_type = getattr(product, "product_type", "")
    return _alignment_score(product_type, evidence_text)


def _jurisdiction_alignment(product, evidence_text: str) -> float:
    jurisdiction = getattr(product, "jurisdiction", "")
    return _alignment_score(jurisdiction, evidence_text)


def _context_profile(product, evidence_text: str) -> Dict[str, float]:
    return {
        "purpose_alignment": _purpose_alignment(product, evidence_text),
        "product_type_alignment": _product_type_alignment(product, evidence_text),
        "jurisdiction_alignment": _jurisdiction_alignment(product, evidence_text),
    }


def _context_adjusted_score(
    base_score: float,
    ingredient_matches: List[str],
    context: Dict[str, float],
    domain_match: bool,
) -> float:
    """
    Context-first retrieval ranking.

    Ingredient matches are supporting signals only.
    Purpose and product-type alignment carry more weight.
    This score is for retrieval ranking, not legal confidence.
    """
    purpose = float(context.get("purpose_alignment", 0.0) or 0.0)
    product_type = float(context.get("product_type_alignment", 0.0) or 0.0)
    jurisdiction = float(context.get("jurisdiction_alignment", 0.0) or 0.0)

    ingredient_bonus = min(len(ingredient_matches) * 0.75, 1.5)

    context_bonus = (
        purpose * 8.0
        + product_type * 3.0
        + jurisdiction * 1.0
    )

    domain_bonus = 1.5 if domain_match else 0.0

    score = (
        float(base_score)
        + ingredient_bonus
        + context_bonus
        + domain_bonus
    )

    # Ingredient-only matches cannot become strong context evidence.
    if ingredient_matches and purpose < 0.25:
        score = min(score, float(base_score) + 1.5)

    if ingredient_matches and product_type < 0.25:
        score = min(score, float(base_score) + 1.5)

    # Reward genuinely coherent product context.
    if purpose >= 0.75 and product_type >= 0.50:
        score += 2.0
    elif purpose >= 0.50:
        score += 1.0

    return round(score, 4)


# =========================================================
# LOAD MAIN CORPUS
# =========================================================

def load_corpus() -> List[Dict]:

    if not os.path.exists(
        CORPUS_PATH
    ):

        print(
            "WARNING: Corpus not found:",
            CORPUS_PATH
        )

        return []

    try:

        with open(
            CORPUS_PATH,
            "r",
            encoding="utf-8"
        ) as file:

            data = json.load(file)

        if not isinstance(
            data,
            list
        ):

            print(
                "ERROR: corpus.json must contain a list"
            )

            return []

        return data

    except Exception as e:

        print(
            "ERROR loading corpus:",
            repr(e)
        )

        return []


# =========================================================
# LOAD TK VECTOR INDEX
# =========================================================

def load_tk_index():

    if not os.path.exists(
        TK_EMBEDDINGS_PATH
    ):

        print(
            "WARNING: TK embeddings not found:",
            TK_EMBEDDINGS_PATH
        )

        return None, []

    if not os.path.exists(
        TK_DOCUMENTS_PATH
    ):

        print(
            "WARNING: TK documents not found:",
            TK_DOCUMENTS_PATH
        )

        return None, []

    try:

        embeddings = np.load(
            TK_EMBEDDINGS_PATH
        )

        with open(
            TK_DOCUMENTS_PATH,
            "r",
            encoding="utf-8"
        ) as file:

            documents = json.load(file)

        if not isinstance(
            documents,
            list
        ):

            print(
                "ERROR: tk_documents.json must contain a list"
            )

            return None, []

        if len(embeddings) != len(documents):

            print(
                "ERROR: TK embedding/document count mismatch:",
                len(embeddings),
                len(documents)
            )

            return None, []

        return embeddings, documents

    except Exception as e:

        print(
            "ERROR loading TK index:",
            repr(e)
        )

        return None, []


# =========================================================
# COSINE SIMILARITY
# =========================================================

def cosine_similarity(
    query_vector,
    document_vectors
):

    query_vector = np.asarray(
        query_vector,
        dtype=np.float32
    )

    document_vectors = np.asarray(
        document_vectors,
        dtype=np.float32
    )

    query_norm = np.linalg.norm(
        query_vector
    )

    document_norms = np.linalg.norm(
        document_vectors,
        axis=1
    )

    if query_norm == 0:
        return np.zeros(
            len(document_vectors)
        )

    denominator = (
        document_norms * query_norm
    )

    denominator = np.where(
        denominator == 0,
        1e-10,
        denominator
    )

    return (
        document_vectors @ query_vector
    ) / denominator


# =========================================================
# TK VECTOR RETRIEVAL
# =========================================================

def retrieve_tk_vector_evidence(
    product,
    domains: List[str],
    top_k: int = 5
) -> List[Dict]:

    # -----------------------------------------------------
    # Only use TK vector search when TK is requested.
    # -----------------------------------------------------

    requested_domains = {
        str(domain).upper()
        for domain in domains
    }

    if "TK" not in requested_domains:

        return []

    embeddings, documents = load_tk_index()

    if embeddings is None or not documents:

        return []

    # -----------------------------------------------------
    # Build semantic query
    # -----------------------------------------------------

    ingredients = getattr(
        product,
        "ingredients",
        []
    )

    product_name = getattr(
        product,
        "product_name",
        ""
    )

    purpose = getattr(
        product,
        "purpose",
        ""
    )

    product_type = getattr(
        product,
        "product_type",
        ""
    )

    query = build_context_aware_query(product)

    # -----------------------------------------------------
    # Create query embedding
    # -----------------------------------------------------

    try:

        query_embedding = embed_query(
            query
        )

    except Exception as e:

        print(
            "ERROR creating TK query embedding:",
            repr(e)
        )

        return []

    # -----------------------------------------------------
    # Similarity
    # -----------------------------------------------------

    similarities = cosine_similarity(
        query_embedding,
        embeddings
    )

    ranked_indices = np.argsort(
        similarities
    )[::-1]

    results = []

    # -----------------------------------------------------
    # Collect top results
    # -----------------------------------------------------

    for index in ranked_indices:

        if len(results) >= top_k:
            break

        similarity = float(
            similarities[index]
        )

        document = documents[index]

        if not isinstance(
            document,
            dict
        ):

            continue

        text = str(
            document.get(
                "text",
                document.get(
                    "page_content",
                    ""
                )
            )
        )

        if not text:
            continue

        source = document.get(
            "source",
            document.get(
                "filename",
                "TK source"
            )
        )

        page = document.get(
            "page",
            document.get(
                "page_number",
                None
            )
        )

        chunk_id = document.get(
            "id",
            ""
        )

        ingredient_matches = find_ingredient_matches(
            ingredients,
            text
        )

        domain_concepts = find_domain_concepts(
            ["TK"],
            text
        )

        matched_terms = domain_concepts.get(
            "TK",
            []
        )

        # -------------------------------------------------
        # Semantic score + lexical bonuses
        # -------------------------------------------------

        base_score = similarity * 10

        if matched_terms:
            base_score += min(
                len(matched_terms) * 1.5,
                4.5
            )

        context = _context_profile(
            product,
            text
        )

        score = _context_adjusted_score(
            base_score,
            ingredient_matches,
            context,
            domain_match=True
        )

        results.append({

            "score": round(
                float(score),
                4
            ),

            "similarity": round(
                similarity,
                4
            ),

            "domain": "TK",

            "source": source,

            "page": page,

            "chunk_id": chunk_id,

            "chunk": document.get(
                "chunk",
                None
            ),

            "matched_terms":
                matched_terms,

            "ingredient_matches":
                ingredient_matches,

            "context_alignment":
                context,

            "ingredient_evidence_is_supporting_only":
                bool(ingredient_matches),

            "domain_match":
                True,

            "retrieval_type":
                "tk_vector",

            "text":
                text[:1800]
        })

    return results


# =========================================================
# CORPUS RETRIEVAL
# =========================================================

def retrieve_corpus_evidence(
    product,
    domains: List[str],
    top_k: int = 8
) -> List[Dict]:

    corpus = load_corpus()

    if not corpus:

        return []

    results = []

    ingredients = getattr(
        product,
        "ingredients",
        []
    )

    requested_domains = {
        str(domain).upper()
        for domain in domains
    }

    for item in corpus:

        text = item.get(
            "page_content",
            ""
        )

        if not text:

            # Some corpus formats may use "text".
            text = item.get(
                "text",
                ""
            )

        if not text:

            continue

        metadata = item.get(
            "metadata",
            {}
        )

        if not isinstance(
            metadata,
            dict
        ):

            metadata = {}

        source = item.get(
            "source",
            metadata.get(
                "filename",
                "Unknown source"
            )
        )

        item_domain = str(
            item.get(
                "domain",
                "UNKNOWN"
            )
        ).upper()

        ingredient_matches = find_ingredient_matches(
            ingredients,
            text
        )

        domain_concepts = find_domain_concepts(
            list(requested_domains),
            text
        )

        concepts = []

        for values in domain_concepts.values():

            concepts.extend(values)

        domain_match = (
            item_domain in requested_domains
        )

        base_score = 0.0

        # -------------------------------------------------
        # Relevant concepts
        # -------------------------------------------------

        if concepts:
            base_score += min(
                len(set(concepts)) * 4,
                12
            )

        # -------------------------------------------------
        # Domain
        # -------------------------------------------------

        if domain_match:
            base_score += 3

        context = _context_profile(
            product,
            text
        )

        score = _context_adjusted_score(
            base_score,
            ingredient_matches,
            context,
            domain_match
        )

        # -------------------------------------------------
        # Relevance gate
        # -------------------------------------------------

        if (
            not ingredient_matches
            and not concepts
        ):

            continue

        results.append({

            "score": score,

            "similarity": None,

            "domain": item_domain,

            "source": source,

            "page": metadata.get(
                "page",
                metadata.get(
                    "page_number",
                    None
                )
            ),

            "chunk_id": item.get(
                "id",
                ""
            ),

            "chunk": metadata.get(
                "chunk",
                None
            ),

            "matched_terms":
                sorted(set(concepts)),

            "ingredient_matches":
                ingredient_matches,

            "context_alignment":
                context,

            "ingredient_evidence_is_supporting_only":
                bool(ingredient_matches),

            "domain_match":
                domain_match,

            "retrieval_type":
                "corpus",

            "text":
                str(text)[:1800]
        })

    results.sort(

        key=lambda item: (

            item["score"],

            len(
                item["ingredient_matches"]
            ),

            len(
                item["matched_terms"]
            ),

            item["domain_match"]
        ),

        reverse=True
    )

    return results[:top_k]


# =========================================================
# MERGE RESULTS
# =========================================================

def merge_evidence(
    corpus_results: List[Dict],
    tk_results: List[Dict],
    top_k: int
) -> List[Dict]:

    combined = []

    seen = set()

    # -----------------------------------------------------
    # Add both sources
    # -----------------------------------------------------

    for item in (
        corpus_results + tk_results
    ):

        key = (

            item.get(
                "source",
                ""
            ),

            item.get(
                "chunk_id",
                ""
            ),

            item.get(
                "page",
                None
            )
        )

        if key in seen:

            continue

        seen.add(key)

        combined.append(item)

    # -----------------------------------------------------
    # Sort by score
    # -----------------------------------------------------

    combined.sort(

        key=lambda item: (

            float(
                item.get(
                    "score",
                    0
                )
            ),

            len(
                item.get(
                    "ingredient_matches",
                    []
                )
            ),

            len(
                item.get(
                    "matched_terms",
                    []
                )
            ),

            float(
                item.get(
                    "context_alignment",
                    {}
                ).get(
                    "purpose_alignment",
                    0.0
                )
                if isinstance(
                    item.get("context_alignment", {}),
                    dict
                )
                else 0.0
            )
        ),

        reverse=True
    )

    return combined[:top_k]


# =========================================================
# MAIN RETRIEVAL FUNCTION
# =========================================================

def retrieve_evidence(
    product,
    domains: List[str],
    top_k: int = 8
) -> List[Dict]:

    """
    Retrieve evidence from:

    1. Main corpus.json
    2. TK semantic vector index

    The TK index is searched automatically
    when "TK" is included in domains.

    Ingredient matches are supporting retrieval signals only.
    Final confidence must be calculated downstream using the full
    product context, evidence quality, source authority, consistency,
    and validated evidence. Retrieval similarity must never be used
    directly as final confidence.
    """

    corpus_results = retrieve_corpus_evidence(

        product,

        domains,

        top_k=top_k
    )

    tk_results = retrieve_tk_vector_evidence(

        product,

        domains,

        top_k=top_k
    )

    return merge_evidence(

        corpus_results,

        tk_results,

        top_k
    )


# =========================================================
# DEBUG TEST
# =========================================================

if __name__ == "__main__":

    print("=" * 70)

    print(
        "IP-SAKTI UNIFIED RETRIEVER TEST"
    )

    print("=" * 70)

    print()

    print(
        "Corpus:",
        CORPUS_PATH
    )

    print(
        "TK index:",
        TK_INDEX_DIR
    )

    print()

    print(
        "TK embeddings exists:",
        os.path.exists(
            TK_EMBEDDINGS_PATH
        )
    )

    print(
        "TK documents exists:",
        os.path.exists(
            TK_DOCUMENTS_PATH
        )
    )

    print()

    class TestProduct:

        product_name = (
            "Turmeric Herbal Skin Cream"
        )

        ingredients = [

            "Turmeric",

            "Aloe vera"
        ]

        purpose = (
            "Cosmetic skin care"
        )

        product_type = (
            "Ayurvedic formulation"
        )

        jurisdiction = "India"

        based_on_traditional_knowledge = (
            "Yes"
        )

    product = TestProduct()

    domains = [

        "TK",

        "ABS"
    ]

    print(
        "Searching domains:",
        domains
    )

    print()

    evidence = retrieve_evidence(

        product,

        domains,

        top_k=8
    )

    print(
        "Evidence found:",
        len(evidence)
    )

    print()

    print("=" * 70)

    for index, item in enumerate(
        evidence,
        start=1
    ):

        print()

        print(
            f"[{index}] "
            f"score={item.get('score')}"
        )

        print(
            "    retrieval_type:",
            item.get(
                "retrieval_type"
            )
        )

        print(
            "    similarity:",
            item.get(
                "similarity"
            )
        )

        print(
            "    domain:",
            item.get(
                "domain"
            )
        )

        print(
            "    source:",
            item.get(
                "source"
            )
        )

        print(
            "    page:",
            item.get(
                "page"
            )
        )

        print(
            "    chunk_id:",
            item.get(
                "chunk_id"
            )
        )

        print(
            "    ingredients:",
            item.get(
                "ingredient_matches"
            )
        )

        print(
            "    concepts:",
            item.get(
                "matched_terms"
            )
        )

        text = item.get(
            "text",
            ""
        )

        print(
            "    text:",
            text[:500].replace(
                "\n",
                " "
            )
        )

    print()

    print("=" * 70)

    print(
        "RETRIEVER TEST COMPLETE"
    )

    print("=" * 70)