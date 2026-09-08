"""
IP-SAKTI Hybrid RAG Retriever

Purpose:
- Use the existing semantic TK index.
- Retrieve TK evidence using BGE embeddings.
- Improve ranking using exact ingredient/alias matches.
- Preserve domain filtering.
- Avoid generic keyword-only false positives.
- Return evidence in a consistent format for main.py.

Expected TK index:
    backend/data/tk_index/tk_embeddings.npy
    backend/data/tk_index/tk_documents.json
"""

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

from data.tk.ip_sakti_tk_pipeline.backend.retriever import search_tk


# =========================================================
# PATHS
# =========================================================

BASE_DIR = Path(__file__).resolve().parent
CORPUS_PATH = BASE_DIR / "data" / "corpus.json"


# =========================================================
# INGREDIENT ALIASES
# =========================================================

INGREDIENT_ALIASES = {
    "turmeric": {
        "turmeric",
        "curcuma",
        "curcuma longa",
        "curcuma_longa",
        "curcumin",
    },
    "aloe": {
        "aloe",
        "aloe vera",
        "aloe_vera",
        "aloe barbadensis",
        "aloe_barbadensis",
        "barbadensis",
    },
    "neem": {
        "neem",
        "azadirachta indica",
        "azadirachta_indica",
    },
    "ashwagandha": {
        "ashwagandha",
        "withania somnifera",
        "withania_somnifera",
    },
    "ginger": {
        "ginger",
        "zingiber officinale",
        "zingiber_officinale",
    },
    "tulsi": {
        "tulsi",
        "holy basil",
        "holy_basil",
        "ocimum sanctum",
        "ocimum_sanctum",
        "ocimum tenuiflorum",
        "ocimum_tenuiflorum",
    },
    "sandalwood": {
        "sandalwood",
        "santalum album",
        "santalum_album",
    },
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
        "indigenous_knowledge",
        "indigenous",
        "folk knowledge",
        "folk_knowledge",
        "herbal knowledge",
        "herbal_knowledge",
        "medicinal plant",
        "medicinal plants",
        "medicinal_plant",
        "medicinal_plants",
        "prior art",
        "prior_art",
        "tkdl",
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
        "genetic_resource",
        "genetic resources",
    },
    "IP": {
        "patent",
        "patents",
        "invention",
        "inventive step",
        "inventive_step",
        "novelty",
        "prior art",
        "prior_art",
        "trademark",
        "trade mark",
        "copyright",
        "industrial design",
        "industrial_design",
        "geographical indication",
        "geographical_indication",
    },
}


# =========================================================
# NORMALIZATION
# =========================================================

def normalize_text(text: Any) -> str:
    """
    Normalize text while preserving underscores.

    Important:
    'Aloe vera' -> 'aloe_vera'
    'Traditional knowledge' -> 'traditional_knowledge'
    """
    if text is None:
        return ""

    text = str(text).lower()

    replacements = {
        "traditional knowledge": "traditional_knowledge",
        "traditional-use": "traditional_use",
        "traditional use": "traditional_use",
        "access and benefit-sharing": "access_benefit_sharing",
        "access and benefit sharing": "access_benefit_sharing",
        "benefit-sharing": "benefit_sharing",
        "benefit sharing": "benefit_sharing",
        "biological resources": "biological_resource",
        "biological resource": "biological_resource",
        "genetic resources": "genetic_resource",
        "genetic resource": "genetic_resource",
        "geographical indications": "geographical_indication",
        "geographical indication": "geographical_indication",
        "industrial design": "industrial_design",
        "inventive step": "inventive_step",
        "prior art": "prior_art",
        "indigenous knowledge": "indigenous_knowledge",
        "folk knowledge": "folk_knowledge",
        "herbal knowledge": "herbal_knowledge",
        "medicinal plants": "medicinal_plants",
        "medicinal plant": "medicinal_plant",
        "aloe-vera": "aloe_vera",
        "aloe vera": "aloe_vera",
        "curcuma longa": "curcuma_longa",
        "withania somnifera": "withania_somnifera",
        "azadirachta indica": "azadirachta_indica",
        "zingiber officinale": "zingiber_officinale",
        "ocimum sanctum": "ocimum_sanctum",
        "ocimum tenuiflorum": "ocimum_tenuiflorum",
        "santalum album": "santalum_album",
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    text = re.sub(r"[^a-z0-9_\s-]", " ", text)
    text = re.sub(r"\s+", " ", text)

    return text.strip()


# =========================================================
# TOKENIZATION
# =========================================================

def tokenize(text: str) -> set:
    normalized = normalize_text(text)
    return set(re.findall(r"\b[a-z][a-z0-9_]{2,}\b", normalized))


# =========================================================
# INGREDIENT CANONICALIZATION
# =========================================================

def canonical_ingredient(ingredient: str) -> str:
    normalized = normalize_text(ingredient)

    for canonical, aliases in INGREDIENT_ALIASES.items():
        if normalized == canonical:
            return canonical

        normalized_aliases = {
            normalize_text(alias) for alias in aliases
        }

        if normalized in normalized_aliases:
            return canonical

        # Handle compound user input.
        for alias in normalized_aliases:
            if (
                normalized == alias
                or alias in normalized.split()
                or alias in normalized
            ):
                return canonical

    return normalized


# =========================================================
# INGREDIENT ALIASES
# =========================================================

def get_ingredient_aliases(ingredient: str) -> set:
    canonical = canonical_ingredient(ingredient)
    aliases = INGREDIENT_ALIASES.get(canonical)

    if aliases:
        return {normalize_text(alias) for alias in aliases}

    return {normalize_text(ingredient)}


# =========================================================
# FIND INGREDIENT MATCHES
# =========================================================

def find_ingredient_matches(
    ingredients: Optional[List[str]],
    text: str,
) -> List[str]:
    if not ingredients:
        return []

    normalized_text = normalize_text(text)
    matches = set()

    for ingredient in ingredients:
        aliases = get_ingredient_aliases(ingredient)

        for alias in aliases:
            if not alias:
                continue

            pattern = r"(?<![a-z0-9_])" + re.escape(alias) + r"(?![a-z0-9_])"

            if re.search(pattern, normalized_text):
                matches.add(alias)

    return sorted(matches)


# =========================================================
# FIND CANONICAL INGREDIENTS IN DOCUMENT
# =========================================================

def find_canonical_ingredient_matches(
    ingredients: Optional[List[str]],
    text: str,
) -> List[str]:
    if not ingredients:
        return []

    normalized_text = normalize_text(text)
    found = set()

    for ingredient in ingredients:
        canonical = canonical_ingredient(ingredient)
        aliases = get_ingredient_aliases(ingredient)

        for alias in aliases:
            pattern = r"(?<![a-z0-9_])" + re.escape(alias) + r"(?![a-z0-9_])"

            if re.search(pattern, normalized_text):
                found.add(canonical)
                break

    return sorted(found)


# =========================================================
# DOMAIN CONCEPT MATCHING
# =========================================================

def find_domain_concepts(
    domains: List[str],
    text: str,
) -> Dict[str, List[str]]:
    normalized_text = normalize_text(text)
    found = {}

    for domain in domains:
        domain = str(domain).upper()
        concepts_found = []

        for concept in DOMAIN_CONCEPTS.get(domain, set()):
            normalized_concept = normalize_text(concept)

            if not normalized_concept:
                continue

            pattern = (
                r"(?<![a-z0-9_])"
                + re.escape(normalized_concept)
                + r"(?![a-z0-9_])"
            )

            if re.search(pattern, normalized_text):
                concepts_found.append(normalized_concept)

        found[domain] = sorted(set(concepts_found))

    return found


# =========================================================
# LOAD CORPUS
# =========================================================

def load_corpus() -> List[Dict]:
    """
    Legacy corpus loader.

    Kept for compatibility with the existing MVP.
    TK semantic retrieval is handled by tk_index.
    """
    if not CORPUS_PATH.exists():
        return []

    try:
        data = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))

        if not isinstance(data, list):
            return []

        return data

    except Exception:
        return []


# =========================================================
# BUILD SEARCH QUERY
# =========================================================

def build_query(
    product=None,
    query: str = "",
    ingredients: Optional[List[str]] = None,
) -> str:
    parts = []

    if query:
        parts.append(query)

    if product is not None:
        product_name = getattr(product, "product_name", "")
        purpose = getattr(product, "purpose", "")
        product_type = getattr(product, "product_type", "")

        if product_name:
            parts.append(product_name)

        if purpose:
            parts.append(purpose)

        if product_type:
            parts.append(product_type)

        product_ingredients = getattr(product, "ingredients", [])

        if product_ingredients:
            parts.extend(product_ingredients)

    if ingredients:
        parts.extend(ingredients)

    # Remove duplicate whitespace.
    return " ".join(str(part).strip() for part in parts if str(part).strip())


# =========================================================
# RERANK SCORE
# =========================================================

def calculate_hybrid_score(
    semantic_score: float,
    ingredient_matches: List[str],
    canonical_matches: List[str],
    concepts: List[str],
    domain_match: bool,
    requested_ingredient_count: int,
) -> float:
    """
    Semantic similarity remains the primary signal.

    Exact ingredient evidence receives a meaningful bonus.

    Multiple requested ingredients are rewarded more strongly
    when they appear in the same document.

    Generic words do not receive a score.
    """
    score = float(semantic_score)

    # -----------------------------------------------------
    # Exact ingredient evidence
    # -----------------------------------------------------
    if canonical_matches:
        # First ingredient match.
        score += 0.10

        # Additional ingredient matches.
        if len(canonical_matches) > 1:
            score += 0.08 * (len(canonical_matches) - 1)

    # -----------------------------------------------------
    # All requested ingredients present
    # -----------------------------------------------------
    if (
        requested_ingredient_count > 0
        and len(canonical_matches) >= requested_ingredient_count
    ):
        score += 0.15

    # -----------------------------------------------------
    # Domain concepts
    # -----------------------------------------------------
    if concepts:
        score += min(0.08, 0.02 * len(set(concepts)))

    # -----------------------------------------------------
    # Correct corpus domain
    # -----------------------------------------------------
    if domain_match:
        score += 0.03

    return round(score, 4)


# =========================================================
# NORMALIZE TK RESULT
# =========================================================

def normalize_tk_result(
    item: Dict,
    ingredients: Optional[List[str]],
    domains: List[str],
) -> Dict:
    text = item.get("page_content") or item.get("text") or ""

    domain = str(item.get("domain", "TK")).upper()

    source = item.get(
        "source",
        item.get("metadata", {}).get("filename", "Unknown source"),
    )

    page = item.get(
        "page",
        item.get("metadata", {}).get("page", None),
    )

    chunk = item.get(
        "chunk",
        item.get("metadata", {}).get("chunk", None),
    )

    similarity = float(item.get("similarity", item.get("score", 0.0)))

    ingredient_matches = find_ingredient_matches(ingredients, text)
    canonical_matches = find_canonical_ingredient_matches(ingredients, text)
    domain_concepts = find_domain_concepts(domains, text)

    concepts = []
    for values in domain_concepts.values():
        concepts.extend(values)

    domain_match = domain in {str(d).upper() for d in domains}

    final_score = calculate_hybrid_score(
        semantic_score=similarity,
        ingredient_matches=ingredient_matches,
        canonical_matches=canonical_matches,
        concepts=concepts,
        domain_match=domain_match,
        requested_ingredient_count=len(ingredients or []),
    )

    return {
        "score": final_score,
        "similarity": round(similarity, 4),
        "retrieval_type": "TK_BGE_HYBRID",
        "domain": domain,
        "source": source,
        "page": page,
        "chunk": chunk,
        "chunk_id": item.get("id", ""),
        "id": item.get("id", ""),
        "ingredient_matches": ingredient_matches,
        "matched_ingredients": canonical_matches,
        "matched_terms": sorted(set(concepts)),
        "domain_match": domain_match,
        "why_retrieved": build_why_retrieved(
            similarity=similarity,
            canonical_matches=canonical_matches,
            concepts=concepts,
            domain_match=domain_match,
        ),
        "text": text[:1800],
        "page_content": text[:1800],
    }


# =========================================================
# WHY RETRIEVED
# =========================================================

def build_why_retrieved(
    similarity: float,
    canonical_matches: List[str],
    concepts: List[str],
    domain_match: bool,
) -> str:
    reasons = []

    if similarity >= 0.60:
        reasons.append("strong semantic similarity")

    if canonical_matches:
        reasons.append(
            "exact ingredient evidence: " + ", ".join(canonical_matches)
        )

    if concepts:
        reasons.append(
            "domain concepts: " + ", ".join(sorted(set(concepts))[:5])
        )

    if domain_match:
        reasons.append("matching domain")

    if not reasons:
        return "Semantic TK retrieval."

    return "; ".join(reasons)


# =========================================================
# TK SEMANTIC SEARCH
# =========================================================

def semantic_tk_retrieve(
    query: str,
    top_k: int = 12,
    min_score: float = 0.20,
) -> List[Dict]:
    if not query.strip():
        return []

    try:
        results = search_tk(query, top_k=top_k, min_score=min_score)

        if not results:
            return []

        return results

    except Exception as e:
        print("TK semantic retrieval error:", repr(e))
        return []


# =========================================================
# HYBRID RETRIEVE
# =========================================================

def hybrid_retrieve(
    query: str,
    domains: Optional[List[str]] = None,
    ingredients: Optional[List[str]] = None,
    top_k: int = 5,
    semantic_top_k: int = 15,
    min_score: float = 0.20,
) -> List[Dict]:
    """
    Main retrieval function.

    Pipeline:

        User query
             |
             v
        BGE semantic search
             |
             v
        retrieve larger candidate set
             |
             v
        ingredient matching
             |
             v
        domain concept matching
             |
             v
        hybrid reranking
             |
             v
        top_k evidence
    """
    if not query.strip():
        return []

    domains = [str(domain).upper() for domain in (domains or [])]
    ingredients = ingredients or []

    # -----------------------------------------------------
    # 1. TK retrieval
    # -----------------------------------------------------
    tk_results = semantic_tk_retrieve(
        query=query,
        top_k=max(semantic_top_k, top_k),
        min_score=min_score,
    )

    results = []

    # -----------------------------------------------------
    # 2. Normalize + rerank
    # -----------------------------------------------------
    for item in tk_results:
        normalized = normalize_tk_result(
            item=item,
            ingredients=ingredients,
            domains=domains or ["TK"],
        )
        results.append(normalized)

    # -----------------------------------------------------
    # 3. Domain filtering
    #
    # TK index currently contains TK material.
    # Do NOT throw away semantic TK results merely because
    # the requested domain list also contains IP / ABS.
    # -----------------------------------------------------
    # Domain matching is used as a ranking signal.
    # The evidence remains available for cross-domain analysis.

    # -----------------------------------------------------
    # 4. Final ranking
    # -----------------------------------------------------
    results.sort(
        key=lambda item: (
            item["score"],
            len(item["matched_ingredients"]),
            len(item["matched_terms"]),
            item["similarity"],
        ),
        reverse=True,
    )

    return results[:top_k]


# =========================================================
# PRODUCT-AWARE RETRIEVAL
# =========================================================

def retrieve_for_product(
    product,
    domains: Optional[List[str]] = None,
    top_k: int = 5,
) -> List[Dict]:
    """
    Convenience function for main.py.
    """
    ingredients = getattr(product, "ingredients", [])

    query = build_query(product=product, ingredients=ingredients)

    return hybrid_retrieve(
        query=query,
        domains=domains or ["TK"],
        ingredients=ingredients,
        top_k=top_k,
        semantic_top_k=max(12, top_k * 3),
    )


# =========================================================
# BACKWARD-COMPATIBLE API
# =========================================================

def search_corpus(
    query: str,
    domains: Optional[List[str]] = None,
    top_k: int = 5,
    ingredients: Optional[List[str]] = None,
) -> List[Dict]:
    """
    Backward-compatible wrapper.

    Existing main.py can continue calling:

        search_corpus(
            query=query,
            domains=domains,
            top_k=5,
            ingredients=product.ingredients
        )
    """
    return hybrid_retrieve(
        query=query,
        domains=domains or ["TK"],
        ingredients=ingredients,
        top_k=top_k,
        semantic_top_k=max(12, top_k * 3),
    )


# =========================================================
# LEGACY NAME
# =========================================================

def retrieve_evidence(
    product,
    domains: List[str],
    top_k: int = 8,
) -> List[Dict]:
    return retrieve_for_product(product=product, domains=domains, top_k=top_k)


# =========================================================
# DEBUG TEST
# =========================================================

if __name__ == "__main__":
    print("=" * 70)
    print("IP-SAKTI HYBRID RAG TEST")
    print("=" * 70)

    query = (
        "Turmeric Aloe vera Ayurvedic "
        "traditional knowledge skin formulation India"
    )

    ingredients = [
        "Turmeric",
        "Aloe vera",
    ]

    domains = [
        "TK",
    ]

    print()
    print("QUERY:")
    print(query)

    print()
    print("-" * 70)
    print("HYBRID SEARCH")
    print("-" * 70)

    results = hybrid_retrieve(
        query=query,
        domains=domains,
        ingredients=ingredients,
        top_k=5,
        semantic_top_k=15,
    )

    print()
    print("Results:", len(results))
    print()

    for index, result in enumerate(results, start=1):
        print(f"#{index} score={result['score']} similarity={result['similarity']}")
        print("Type:", result["retrieval_type"])
        print("Domain:", result["domain"])
        print("Source:", result["source"])
        print("Page:", result["page"])
        print("ID:", result["id"])
        print("Matched ingredients:", result["matched_ingredients"])
        print("Ingredient aliases:", result["ingredient_matches"])
        print("Domain concepts:", result["matched_terms"])
        print("Why:", result["why_retrieved"])
        print("Text:", result["text"][:500])
        print("-" * 70)

    print()
    print("HYBRID RAG TEST COMPLETE")


# =========================================================
# COMPATIBILITY FUNCTION FOR TK RETRIEVER
# =========================================================

def embed_query(text: str):
    """
    Embed a single query using the same embedding model
    used by the corpus/index.

    This function exists for compatibility with the TK
    semantic retriever.
    """
    if not isinstance(text, str):
        text = str(text)

    text = text.strip()

    if not text:
        raise ValueError("Query text cannot be empty.")

    # Try the existing embedding function used by this project.
    if "embed_text" in globals():
        return embed_text(text)

    if "embed" in globals():
        return embed(text)

    if "get_embedding" in globals():
        return get_embedding(text)

    raise RuntimeError(
        "No compatible embedding function was found in embeddings.py. "
        "Please check the embedding implementation."
    )