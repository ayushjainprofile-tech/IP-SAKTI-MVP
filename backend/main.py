from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator
from typing import Any, Dict, Iterable, List
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from urllib.parse import urlparse
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import json
import os
import re
import logging
from functools import lru_cache

import ollama

# =========================================================
# AGENTIC AI CHAT ADDITION
# =========================================================
# NOTE: The Agentic AI chat orchestrator (run_agent_chat) and its
# request schema (AgentChatRequest) are defined further down in this
# same file, directly on top of the EXISTING search_corpus,
# validate_evidence, generate_llm_reasoning, calculate_confidence,
# and run_agentic_research (web search) functions. No separate
# package/module is required and no existing function is duplicated.


# =========================================================
# CONVERSATION API
# =========================================================

try:
    from conversation_api import router as conversation_router
except Exception as e:
    conversation_router = None
    logging.warning(
        "Conversation router unavailable: %r",
        e
    )


# =========================================================
# OPTIONAL BGE EMBEDDING ENGINE
# =========================================================

try:
    from embeddings import (
        semantic_search,
        EMBEDDING_MODEL,
        EMBEDDINGS_AVAILABLE,
    )

except Exception as e:

    EMBEDDINGS_AVAILABLE = False
    EMBEDDING_MODEL = None

    logging.warning(
        "Embedding engine unavailable: %r",
        e
    )

    def semantic_search(
        query,
        documents,
        top_k=5,
        min_score=0.35
    ):
        return []


# =========================================================
# LOGGING
# =========================================================

logging.basicConfig(
    level=os.getenv(
        "LOG_LEVEL",
        "INFO"
    ).upper(),

    format=(
        "%(asctime)s | "
        "%(levelname)s | "
        "%(message)s"
    )
)

logger = logging.getLogger(
    "ip-sakti"
)


# =========================================================
# CONFIGURATION
# =========================================================

OLLAMA_MODEL = os.getenv(
    "OLLAMA_MODEL",
    "llama3.2:1b"
)

# Single source of truth for API version.
#
# Default intentionally matches the earlier 0.7.x build.
# If you want another version, set:
#
# APP_VERSION=1.0.0
#
APP_VERSION = os.getenv(
    "APP_VERSION",
    "0.7.0"
)

TOP_K = max(
    1,
    int(
        os.getenv(
            "TOP_K",
            "5"
        )
    )
)

MIN_SEMANTIC_SIMILARITY = float(
    os.getenv(
        "MIN_SEMANTIC_SIMILARITY",
        "0.35"
    )
)

MAX_EVIDENCE_TEXT = max(
    500,
    int(
        os.getenv(
            "MAX_EVIDENCE_TEXT",
            "1800"
        )
    )
)

MAX_QUERY_LENGTH = max(
    500,
    int(
        os.getenv(
            "MAX_QUERY_LENGTH",
            "1800"
        )
    )
)


# =========================================================
# APP
# =========================================================

app = FastAPI(

    title="IP-SAKTI MVP API",

    version=APP_VERSION,

    description=(
        "Evidence-first IP / Traditional Knowledge / "
        "Access and Benefit Sharing assessment prototype."
    )
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


if conversation_router is not None:

    app.include_router(
        conversation_router
    )


# =========================================================
# INPUT MODEL
# =========================================================

class ProductInput(BaseModel):

    product_name: str = Field(
        ...,
        min_length=1,
        max_length=200
    )

    ingredients: List[str] = Field(
        default_factory=list,
        max_length=50
    )

    purpose: str = Field(
        ...,
        min_length=1,
        max_length=1000
    )

    product_type: str = Field(
        ...,
        min_length=1,
        max_length=200
    )

    jurisdiction: str = Field(
        default="India",
        max_length=200
    )

    based_on_traditional_knowledge: str = Field(
        default="unknown",
        max_length=50
    )

    @field_validator(
        "product_name",
        "purpose",
        "product_type",
        "jurisdiction"
    )
    @classmethod
    def clean_text(cls, value):

        value = str(
            value
        ).strip()

        if not value:
            raise ValueError(
                "Field cannot be empty."
            )

        return value

    @field_validator(
        "ingredients"
    )
    @classmethod
    def clean_ingredients(
        cls,
        values
    ):

        cleaned = []
        seen = set()

        for value in values or []:

            value = str(
                value
            ).strip()

            if not value:
                continue

            normalized = normalize_text(
                value
            )

            if (
                normalized
                and normalized not in seen
            ):

                cleaned.append(
                    value
                )

                seen.add(
                    normalized
                )

        return cleaned




# Agentic AI configuration
AGENTIC_AI_AVAILABLE = True
AGENTIC_AI_ENABLED = (
    os.getenv("AGENTIC_AI_ENABLED", "false").strip().lower()
    in {"1", "true", "yes", "on"}
)
AGENTIC_MAX_WEB_EVIDENCE = max(1, min(10, int(os.getenv("AGENTIC_MAX_WEB_EVIDENCE", "5"))))

# =========================================================
# CORPUS
# =========================================================

BASE_DIR = os.path.dirname(
    os.path.abspath(__file__)
)

CORPUS_PATH = os.path.join(
    BASE_DIR,
    "data",
    "corpus.json"
)


@lru_cache(maxsize=1)
def _load_corpus():

    if not os.path.exists(
        CORPUS_PATH
    ):

        logger.error(
            "Corpus not found: %s",
            CORPUS_PATH
        )

        return []

    try:

        with open(
            CORPUS_PATH,
            "r",
            encoding="utf-8"
        ) as f:

            data = json.load(f)

        if not isinstance(
            data,
            list
        ):

            logger.error(
                "corpus.json must contain a list."
            )

            return []

        data = [
            item
            for item in data
            if isinstance(
                item,
                dict
            )
        ]

        logger.info(
            "Loaded %d corpus chunks.",
            len(data)
        )

        return data

    except Exception as e:

        logger.exception(
            "Corpus loading failed: %r",
            e
        )

        return []


def load_corpus(
    force_reload=False
):

    if force_reload:

        _load_corpus.cache_clear()

    return _load_corpus()


# =========================================================
# NORMALIZATION
# =========================================================

def normalize_text(text):

    if text is None:
        return ""

    text = str(
        text
    ).lower().strip()

    replacements = {

        "traditional knowledge":
            "traditional_knowledge",

        "traditional-knowledge":
            "traditional_knowledge",

        "access and benefit sharing":
            "access_benefit_sharing",

        "access and benefit-sharing":
            "access_benefit_sharing",

        "benefit-sharing":
            "benefit_sharing",

        "benefit sharing":
            "benefit_sharing",

        "biological diversity":
            "biodiversity",

        "bio-diversity":
            "biodiversity",

        "biological resource":
            "biological_resource",

        "biological-resources":
            "biological_resource",

        "genetic resource":
            "genetic_resource",

        "genetic-resources":
            "genetic_resource",

        "geographical indications":
            "geographical_indication",

        "geographical indication":
            "geographical_indication",

        "trade mark":
            "trademark",

        "trade-mark":
            "trademark",

        "intellectual property":
            "intellectual_property",

        "prior art":
            "prior_art",

        "inventive step":
            "inventive_step",

        "traditional use":
            "traditional_use",

        "traditional medicine":
            "traditional_medicine",

        "aloe-vera":
            "aloe_vera",

        "curcuma longa":
            "curcuma_longa",

        "aloe barbadensis":
            "aloe_barbadensis"
    }

    for old, new in replacements.items():

        text = text.replace(
            old,
            new
        )

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
# STOPWORDS
# =========================================================

STOPWORDS = {

    "the",
    "and",
    "for",
    "with",
    "from",
    "this",
    "that",
    "are",
    "was",
    "were",
    "has",
    "have",
    "into",
    "your",
    "user",
    "product",
    "purpose",
    "based",
    "india",
    "yes",
    "true",
    "false",
    "unknown",

    "skin",
    "care",
    "cream",
    "cosmetic",
    "formulation",
    "type",

    "information",
    "use",
    "used",
    "using",
    "may",
    "can",
    "including",
    "under",

    "its",
    "their",
    "also",
    "such"
}


# =========================================================
# TOKENIZATION
# =========================================================

def tokenize(text):

    normalized = normalize_text(
        text
    )

    words = re.findall(
        r"\b[a-z][a-z0-9_]{2,}\b",
        normalized
    )

    return {
        word
        for word in words
        if word not in STOPWORDS
    }


def phrase_in_text(
    text,
    phrase
):

    normalized_text = normalize_text(
        text
    )

    normalized_phrase = normalize_text(
        phrase
    )

    if not normalized_phrase:
        return False

    pattern = (
        r"(?<![a-z0-9_])"
        + re.escape(
            normalized_phrase
        )
        + r"(?![a-z0-9_])"
    )

    return bool(
        re.search(
            pattern,
            normalized_text
        )
    )


# =========================================================
# DOMAIN KNOWLEDGE
# =========================================================

STRONG_DOMAIN_TERMS = {

    "IP": {

        "patent",
        "invention",
        "inventive_step",
        "novelty",
        "prior_art",
        "trademark",
        "copyright",
        "design",
        "geographical_indication",
        "intellectual_property"
    },

    "TK": {

        "traditional_knowledge",
        "traditional_use",
        "ayurveda",
        "ayurvedic",
        "herbal",
        "indigenous",
        "folk",
        "medicinal",
        "traditional_medicine",
        "ethnobotanical"
    },

    "ABS": {

        "biodiversity",
        "biological_resource",
        "genetic_resource",
        "access_benefit_sharing",
        "benefit_sharing",
        "biological",
        "genetic"
    }
}


# =========================================================
# DOMAIN ROUTING SIGNALS
# =========================================================

DOMAIN_ROUTING_SIGNALS = {

    "IP": {

        "patent",
        "invention",
        "trademark",
        "copyright",
        "design",
        "geographical_indication",
        "intellectual_property",
        "prior_art",
        "novelty",
        "inventive_step"
    },

    "TK": {

        "traditional_knowledge",
        "traditional_use",
        "ayurveda",
        "ayurvedic",
        "traditional_medicine",
        "folk",
        "indigenous",
        "ethnobotanical"
    },

    "ABS": {

        "biodiversity",
        "biological_resource",
        "genetic_resource",
        "access_benefit_sharing",
        "benefit_sharing",
        "genetic"
    }
}


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

    "curcuma": {

        "turmeric",
        "curcuma",
        "curcuma_longa",
        "curcumin"
    },

    "curcuma longa": {

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
    },

    "aloe vera": {

        "aloe",
        "aloe_vera",
        "aloe_barbadensis",
        "barbadensis"
    }
}


def get_ingredient_aliases(
    ingredient
):

    normalized = normalize_text(
        ingredient
    )

    aliases = {
        normalized
    }

    if normalized in INGREDIENT_ALIASES:

        aliases.update(
            INGREDIENT_ALIASES[
                normalized
            ]
        )

    for key, values in INGREDIENT_ALIASES.items():

        if (
            phrase_in_text(
                normalized,
                key
            )
            or normalized in values
        ):

            aliases.update(
                values
            )

    return {
        normalize_text(
            value
        )
        for value in aliases
        if value
    }


# =========================================================
# DOCUMENT HELPERS
# =========================================================

def get_document_text(
    item
):

    text = item.get(
        "page_content",
        ""
    )

    if not text:

        text = item.get(
            "text",
            ""
        )

    return str(
        text or ""
    )


def get_document_id(
    item
):

    return str(
        item.get(
            "id",
            item.get(
                "chunk_id",
                ""
            )
        )
        or ""
    ).strip()


def get_document_domain(
    item
):

    metadata = item.get(
        "metadata",
        {}
    ) or {}

    domain = item.get(
        "domain",
        metadata.get(
            "domain",
            "UNKNOWN"
        )
    )

    return str(
        domain or "UNKNOWN"
    ).upper().strip()


def get_document_source(
    item
):

    metadata = item.get(
        "metadata",
        {}
    ) or {}

    return str(
        item.get(
            "source",
            metadata.get(
                "filename",
                "Unknown source"
            )
        )
        or "Unknown source"
    )


def get_document_page(
    item
):

    metadata = item.get(
        "metadata",
        {}
    ) or {}

    return item.get(
        "page",
        metadata.get(
            "page"
        )
    )


def get_document_chunk(
    item
):

    metadata = item.get(
        "metadata",
        {}
    ) or {}

    return item.get(
        "chunk",
        metadata.get(
            "chunk"
        )
    )


# =========================================================
# DOMAIN DETECTION
# =========================================================

def detect_domains(
    product
):

    text = normalize_text(
        " ".join([
            product.product_name,
            " ".join(
                product.ingredients
            ),
            product.purpose,
            product.product_type,
            product.jurisdiction
        ])
    )

    domains = []

    tk_answer = normalize_text(
        product.based_on_traditional_knowledge
    )

    if tk_answer in {
        "yes",
        "true",
        "y",
        "1"
    }:

        domains.append(
            "TK"
        )

    for domain, signals in (
        DOMAIN_ROUTING_SIGNALS.items()
    ):

        if any(
            phrase_in_text(
                text,
                signal
            )
            for signal in signals
        ):

            if domain not in domains:

                domains.append(
                    domain
                )

    # Known biological-resource ingredients
    # are routing signals ONLY.
    #
    # They do NOT constitute ABS evidence.
    ingredient_signals = {

        "turmeric",
        "curcuma",
        "curcuma_longa",
        "curcumin",
        "aloe",
        "aloe_vera",
        "aloe_barbadensis"
    }

    ingredient_text = normalize_text(
        " ".join(
            product.ingredients
        )
    )

    if any(
        phrase_in_text(
            ingredient_text,
            signal
        )
        for signal in ingredient_signals
    ):

        if "ABS" not in domains:

            domains.append(
                "ABS"
            )

    # IP is always a baseline
    # assessment domain.
    if "IP" not in domains:

        domains.append(
            "IP"
        )

    return domains


# =========================================================
# PRODUCT CLASSIFICATION
# =========================================================

def classify_product(
    product
):

    tk_value = normalize_text(
        product.based_on_traditional_knowledge
    )

    if tk_value in {
        "yes",
        "true",
        "y",
        "1"
    }:

        tk_status = "YES"

    elif tk_value in {
        "no",
        "false",
        "n",
        "0"
    }:

        tk_status = "NO"

    else:

        tk_status = "UNKNOWN"

    return {

        "product_type":
            product.product_type,

        "traditional_knowledge":
            product.based_on_traditional_knowledge,

        "traditional_knowledge_status":
            tk_status,

        "jurisdiction":
            product.jurisdiction,

        "classification_note":
            (
                "Prototype classification based on "
                "user-provided information. This is a "
                "routing signal, not a legal determination."
            )
    }


# =========================================================
# SEARCH QUERY
# =========================================================

def build_search_query(
    product,
    domains
):

    parts = [

        product.product_name,

        " ".join(
            product.ingredients
        ),

        product.purpose,

        product.product_type
    ]

    if "TK" in domains:

        parts.append(
            "traditional knowledge traditional use"
        )

    if "ABS" in domains:

        parts.append(
            "biological resource biodiversity "
            "access benefit sharing"
        )

    if "IP" in domains:

        parts.append(
            "intellectual property patent trademark"
        )

    query = " ".join(
        str(part).strip()
        for part in parts
        if str(part).strip()
    )

    return query[
        :MAX_QUERY_LENGTH
    ]


# =========================================================
# INGREDIENT MATCHING
# =========================================================

def find_ingredient_matches(
    text,
    ingredients
):

    normalized_text = normalize_text(
        text
    )

    matches = set()

    for ingredient in ingredients:

        aliases = get_ingredient_aliases(
            ingredient
        )

        for alias in aliases:

            if phrase_in_text(
                normalized_text,
                alias
            ):

                matches.add(
                    alias
                )

    return sorted(
        matches
    )


# =========================================================
# DOMAIN MATCHING
# =========================================================

def find_domain_matches(
    text,
    domains
):

    normalized_text = normalize_text(
        text
    )

    result = {}

    for domain in domains:

        matched = []

        for term in STRONG_DOMAIN_TERMS.get(
            domain,
            set()
        ):

            if phrase_in_text(
                normalized_text,
                term
            ):

                matched.append(
                    term
                )

        result[
            domain
        ] = sorted(
            set(
                matched
            )
        )

    return result


def get_supported_domains_from_item(
    item,
    detected_domains
):
    """
    CRITICAL DISTINCTION:

    document domain metadata != actual evidence.

    A corpus item tagged IP is not evidence for IP
    unless the text itself contains relevant IP terms.

    Ingredient matches are intentionally NOT treated
    as domain evidence.
    """

    domain_matches = item.get(
        "domain_matches",
        {}
    ) or {}

    supported = []

    for domain in detected_domains:

        terms = domain_matches.get(
            domain,
            []
        )

        if terms:

            supported.append(
                domain
            )

    return supported


# =========================================================
# KEYWORD SCORING
# =========================================================

def calculate_keyword_score(
    query_tokens,
    document_text,
    document_domain,
    domains,
    ingredients
):

    normalized_text = normalize_text(
        document_text
    )

    document_tokens = tokenize(
        normalized_text
    )

    matched_terms = (
        query_tokens.intersection(
            document_tokens
        )
    )

    score = min(
        len(
            matched_terms
        ) * 0.45,
        5.0
    )

    # Metadata alignment contributes to ranking,
    # but NOT to evidence validation.
    domain_match = (
        document_domain in domains
    )

    if domain_match:

        score += 2.5

    ingredient_matches = (
        find_ingredient_matches(
            normalized_text,
            ingredients
        )
    )

    # Retrieval signal only.
    score += min(
        len(
            ingredient_matches
        ) * 4.0,
        12.0
    )

    domain_matches = (
        find_domain_matches(
            normalized_text,
            domains
        )
    )

    for domain in domains:

        score += min(
            len(
                domain_matches.get(
                    domain,
                    []
                )
            ) * 1.25,
            5.0
        )

    return {

        "score":
            round(
                score,
                4
            ),

        "matched_terms":
            sorted(
                matched_terms
            )[:30],

        "ingredient_matches":
            ingredient_matches,

        "domain_matches":
            domain_matches,

        "domain_match":
            domain_match
    }


# =========================================================
# EVIDENCE QUALITY
# =========================================================

def calculate_evidence_quality(
    item
):

    ingredient_count = len(
        item.get(
            "ingredient_matches",
            []
        )
    )

    domain_match = bool(
        item.get(
            "domain_match",
            False
        )
    )

    domain_term_count = sum(
        len(values)
        for values in (
            item.get(
                "domain_matches",
                {}
            ) or {}
        ).values()
    )

    try:

        similarity = float(
            item.get(
                "similarity",
                0.0
            ) or 0.0
        )

    except (
        TypeError,
        ValueError
    ):

        similarity = 0.0

    quality = 0.0

    quality += min(
        ingredient_count * 0.20,
        0.40
    )

    quality += (
        0.25
        if domain_match
        else 0.0
    )

    quality += min(
        domain_term_count * 0.05,
        0.20
    )

    quality += (
        min(
            max(
                similarity,
                0.0
            ),
            1.0
        ) * 0.15
    )

    return round(
        min(
            quality,
            1.0
        ),
        4
    )


# =========================================================
# CORPUS SEARCH
# =========================================================

def search_corpus(
    query,
    domains,
    ingredients=None,
    top_k=5
):

    if ingredients is None:

        ingredients = []

    query = str(
        query or ""
    ).strip()

    if not query:

        return []

    domains = [
        str(domain).upper().strip()
        for domain in domains
        if str(domain).strip()
    ]

    corpus = load_corpus()

    if not corpus:

        logger.warning(
            "Empty corpus."
        )

        return []

    query_tokens = tokenize(
        query
    )

    # -----------------------------------------------------
    # 1. DOMAIN FILTER
    # -----------------------------------------------------

    candidates = []

    for item in corpus:

        text = get_document_text(
            item
        )

        if not text:
            continue

        document_domain = (
            get_document_domain(
                item
            )
        )

        if (
            document_domain
            in domains
        ):

            candidates.append(
                item
            )

    # Fast pre-filtering: filter candidate chunks in milliseconds before detailed scoring
    ing_lower = [str(ing).lower() for ing in ingredients if str(ing).strip()]
    if ing_lower or query_tokens:
        fast_candidates = []
        for item in candidates:
            t_lower = get_document_text(item).lower()
            if any(ing in t_lower for ing in ing_lower) or any(tok in t_lower for tok in query_tokens):
                fast_candidates.append(item)
        if fast_candidates:
            candidates = fast_candidates[:200]

    logger.info(
        "Domain-aligned candidates: %d",
        len(candidates)
    )

    # -----------------------------------------------------
    # 2. KEYWORD SEARCH
    # -----------------------------------------------------

    keyword_results = {}

    for index, item in enumerate(
        candidates
    ):

        text = get_document_text(
            item
        )

        document_domain = (
            get_document_domain(
                item
            )
        )

        scoring = calculate_keyword_score(

            query_tokens=query_tokens,

            document_text=text,

            document_domain=document_domain,

            domains=domains,

            ingredients=ingredients
        )

        has_ingredient_evidence = bool(
            scoring[
                "ingredient_matches"
            ]
        )

        has_domain_evidence = any(

            scoring[
                "domain_matches"
            ].get(
                domain,
                []
            )

            for domain in domains
        )

        # HARD RELEVANCE GATE.
        #
        # Generic keyword overlap alone
        # is NOT enough.
        if not (
            has_ingredient_evidence
            or (
                scoring[
                    "domain_match"
                ]
                and has_domain_evidence
            )
        ):

            continue

        item_id = get_document_id(
            item
        )

        if not item_id:

            item_id = (
                f"{get_document_source(item)}-"
                f"{get_document_page(item)}-"
                f"{get_document_chunk(item)}-"
                f"{index}"
            )

        keyword_results[
            item_id
        ] = {

            "id":
                item_id,

            "keyword_score":
                scoring[
                    "score"
                ],

            "matched_terms":
                scoring[
                    "matched_terms"
                ],

            "ingredient_matches":
                scoring[
                    "ingredient_matches"
                ],

            "domain_matches":
                scoring[
                    "domain_matches"
                ],

            "domain_match":
                scoring[
                    "domain_match"
                ],

            "domain":
                document_domain,

            "source":
                get_document_source(
                    item
                ),

            "page":
                get_document_page(
                    item
                ),

            "chunk":
                get_document_chunk(
                    item
                ),

            "text":
                text[
                    :MAX_EVIDENCE_TEXT
                ]
        }

    logger.info(
        "Keyword evidence candidates: %d",
        len(
            keyword_results
        )
    )

    # -----------------------------------------------------
    # 3. BGE SEMANTIC SEARCH
    # -----------------------------------------------------

    semantic_results = []

    if (
        EMBEDDINGS_AVAILABLE
        and candidates
    ):

        semantic_documents = []

        for index, item in enumerate(
            candidates[:60]
        ):

            item_id = get_document_id(
                item
            )

            if not item_id:

                item_id = (
                    f"{get_document_source(item)}-"
                    f"{get_document_page(item)}-"
                    f"{get_document_chunk(item)}-"
                    f"{index}"
                )

            semantic_documents.append({

                "id":
                    item_id,

                "domain":
                    get_document_domain(
                        item
                    ),

                "source":
                    get_document_source(
                        item
                    ),

                "page":
                    get_document_page(
                        item
                    ),

                "chunk":
                    get_document_chunk(
                        item
                    ),

                "page_content":
                    get_document_text(
                        item
                    )
            })

        try:

            semantic_results = semantic_search(

                query=query,

                documents=semantic_documents,

                top_k=max(
                    top_k * 3,
                    10
                ),

                min_score=(
                    MIN_SEMANTIC_SIMILARITY
                )
            )

            logger.info(
                "BGE candidates: %d",
                len(
                    semantic_results
                )
            )

        except Exception as e:

            logger.exception(
                "BGE search failed: %r",
                e
            )

            semantic_results = []

    semantic_by_id = {}

    for item in semantic_results:

        item_id = str(
            item.get(
                "id",
                ""
            )
        ).strip()

        if item_id:

            semantic_by_id[
                item_id
            ] = item

    # -----------------------------------------------------
    # 4. MERGE
    # -----------------------------------------------------

    merged = {}

    all_ids = (
        set(
            keyword_results.keys()
        )
        |
        set(
            semantic_by_id.keys()
        )
    )

    for item_id in all_ids:

        keyword_item = (
            keyword_results.get(
                item_id
            )
        )

        semantic_item = (
            semantic_by_id.get(
                item_id
            )
        )

        if keyword_item:

            result = dict(
                keyword_item
            )

        elif semantic_item:

            result = {

                "id":
                    item_id,

                "keyword_score":
                    0.0,

                "matched_terms":
                    [],

                "ingredient_matches":
                    [],

                "domain_matches":
                    {},

                "domain_match":
                    True,

                "domain":
                    str(
                        semantic_item.get(
                            "domain",
                            "UNKNOWN"
                        )
                    ).upper(),

                "source":
                    semantic_item.get(
                        "source",
                        "Unknown source"
                    ),

                "page":
                    semantic_item.get(
                        "page"
                    ),

                "chunk":
                    semantic_item.get(
                        "chunk"
                    ),

                "text":
                    str(
                        semantic_item.get(
                            "page_content",
                            semantic_item.get(
                                "text",
                                ""
                            )
                        )
                    )[
                        :MAX_EVIDENCE_TEXT
                    ]
            }

        else:

            continue

        try:

            similarity = float(
                semantic_item.get(
                    "similarity",
                    0.0
                )
            ) if semantic_item else 0.0

        except (
            TypeError,
            ValueError
        ):

            similarity = 0.0

        result[
            "similarity"
        ] = (
            round(
                similarity,
                4
            )
            if semantic_item
            else None
        )

        # Recalculate evidence from FINAL text.
        result[
            "ingredient_matches"
        ] = sorted(
            set(
                result.get(
                    "ingredient_matches",
                    []
                )
            )
            |
            set(
                find_ingredient_matches(
                    result.get(
                        "text",
                        ""
                    ),
                    ingredients
                )
            )
        )

        result[
            "domain_matches"
        ] = find_domain_matches(

            result.get(
                "text",
                ""
            ),

            domains
        )

        has_ingredient_evidence = bool(
            result[
                "ingredient_matches"
            ]
        )

        has_domain_evidence = any(

            result[
                "domain_matches"
            ].get(
                domain,
                []
            )

            for domain in domains
        )

        domain_match = (
            result.get(
                "domain",
                "UNKNOWN"
            )
            in domains
        )

        # -------------------------------------------------
        # CRITICAL EVIDENCE GATE
        #
        # Semantic similarity by itself is NOT evidence.
        #
        # Metadata domain alignment by itself is NOT
        # evidence.
        # -------------------------------------------------

        if not (
            has_ingredient_evidence
            or (
                domain_match
                and has_domain_evidence
            )
        ):

            continue

        result[
            "domain_match"
        ] = domain_match

        keyword_score = float(
            result.get(
                "keyword_score",
                0.0
            )
        )

        semantic_scaled = (
            similarity * 10.0
        )

        ingredient_bonus = min(
            len(
                result[
                    "ingredient_matches"
                ]
            ) * 2.5,
            7.5
        )

        domain_bonus = (
            2.5
            if domain_match
            else 0.0
        )

        if (
            semantic_item
            and keyword_item
        ):

            combined_score = (

                0.55
                * semantic_scaled

                +

                0.25
                * min(
                    keyword_score,
                    10.0
                )

                +

                ingredient_bonus

                +

                domain_bonus
            )

            retrieval_type = (
                "HYBRID"
            )

        elif semantic_item:

            combined_score = (

                0.75
                * semantic_scaled

                +

                ingredient_bonus

                +

                domain_bonus
            )

            retrieval_type = (
                "BGE_SEMANTIC"
            )

        else:

            combined_score = (

                keyword_score

                +

                ingredient_bonus

                +

                domain_bonus
            )

            retrieval_type = (
                "KEYWORD"
            )

        result[
            "score"
        ] = round(
            combined_score,
            4
        )

        result[
            "retrieval_type"
        ] = retrieval_type

        result[
            "evidence_quality"
        ] = calculate_evidence_quality(
            result
        )

        evidence_basis = []

        if result[
            "ingredient_matches"
        ]:

            evidence_basis.append(
                "ingredient_match"
            )

        if any(

            result[
                "domain_matches"
            ].get(
                domain,
                []
            )

            for domain in domains
        ):

            evidence_basis.append(
                "domain_term_match"
            )

        if semantic_item:

            evidence_basis.append(
                "semantic_similarity"
            )

        if result[
            "matched_terms"
        ]:

            evidence_basis.append(
                "keyword_overlap"
            )

        result[
            "evidence_basis"
        ] = evidence_basis

        # NEW:
        # Explicitly record which detected domains
        # this evidence actually supports.
        result[
            "supported_domains"
        ] = get_supported_domains_from_item(
            result,
            domains
        )

        merged[
            item_id
        ] = result

    # -----------------------------------------------------
    # 5. RANK
    # -----------------------------------------------------

    results = list(
        merged.values()
    )

    results.sort(

        key=lambda item: (

            float(
                item.get(
                    "score",
                    0.0
                )
            ),

            float(
                item.get(
                    "evidence_quality",
                    0.0
                )
            ),

            len(
                item.get(
                    "ingredient_matches",
                    []
                )
            ),

            float(
                item.get(
                    "similarity",
                    0.0
                )
                or 0.0
            )
        ),

        reverse=True
    )

    # -----------------------------------------------------
    # 6. SOURCE DIVERSITY
    # -----------------------------------------------------

    selected = []

    source_counts = {}

    for item in results:

        source = item.get(
            "source",
            "Unknown source"
        )

        if source_counts.get(
            source,
            0
        ) >= 3:

            continue

        selected.append(
            item
        )

        source_counts[
            source
        ] = (
            source_counts.get(
                source,
                0
            )
            + 1
        )

        if len(
            selected
        ) >= top_k:

            break

    # Fill remaining slots.
    if len(
        selected
    ) < top_k:

        selected_ids = {
            item[
                "id"
            ]
            for item in selected
        }

        for item in results:

            if item[
                "id"
            ] in selected_ids:

                continue

            selected.append(
                item
            )

            if len(
                selected
            ) >= top_k:

                break

    return selected[
        :top_k
    ]


# =========================================================
# DOMAIN EVIDENCE SUMMARY
# =========================================================

def build_domain_evidence_summary(
    evidence,
    domains
):

    summary = {}

    for domain in domains:

        domain_items = []

        for item in evidence:

            domain_terms = (
                item.get(
                    "domain_matches",
                    {}
                ).get(
                    domain,
                    []
                )
            )

            if domain_terms:

                domain_items.append(
                    item
                )

        sources = sorted(
            set(
                item.get(
                    "source",
                    "Unknown source"
                )
                for item in domain_items
            )
        )

        terms = sorted(
            set(
                term
                for item in domain_items
                for term in item.get(
                    "domain_matches",
                    {}
                ).get(
                    domain,
                    []
                )
            )
        )

        ingredient_items = [
            item
            for item in evidence
            if item.get(
                "ingredient_matches"
            )
        ]

        summary[
            domain
        ] = {

            "supported":
                bool(domain_items),

            "evidence_count":
                len(domain_items),

            "sources":
                sources,

            "matched_domain_terms":
                terms,

            "ingredient_evidence_count":
                len(ingredient_items)
                if domain == "ABS"
                else 0
        }

    return summary


# =========================================================
# EVIDENCE VALIDATION
# =========================================================

def validate_evidence(
    evidence,
    domains
):

    domain_summary = (
        build_domain_evidence_summary(
            evidence,
            domains
        )
    )

    supported_domains = [
        domain
        for domain in domains
        if domain_summary.get(
            domain,
            {}
        ).get(
            "supported",
            False
        )
    ]

    unsupported_domains = [
        domain
        for domain in domains
        if domain not in supported_domains
    ]

    strong_items = 0
    ingredient_items = 0

    # IMPORTANT:
    # This is now actual domain evidence,
    # not metadata alignment.
    domain_evidence_items = 0

    for item in evidence:

        if float(
            item.get(
                "score",
                0.0
            )
        ) >= 8.0:

            strong_items += 1

        if item.get(
            "ingredient_matches"
        ):

            ingredient_items += 1

        if item.get(
            "supported_domains"
        ):

            domain_evidence_items += 1

    if not evidence:

        status = "UNSUPPORTED"

        message = (
            "No sufficiently relevant evidence "
            "was found for the detected domain(s) "
            "in the current corpus."
        )

    elif not supported_domains:

        status = "UNSUPPORTED"

        message = (
            "Retrieved material did not provide "
            "direct domain evidence for the detected "
            "domain(s)."
        )

    elif unsupported_domains:

        # NEW:
        # Mixed-domain result.
        #
        # Example:
        # detected = IP, TK, ABS
        # supported = IP
        # unsupported = TK, ABS
        status = "PARTIAL"

        message = (
            "Evidence was found for only a subset "
            "of the detected domain(s). Unsupported "
            "domains must not be inferred from the "
            "available evidence."
        )

    elif (
        strong_items >= 1
        and domain_evidence_items >= 1
    ):

        status = "EVIDENCE_FOUND"

        message = (
            "Relevant domain-specific evidence was "
            "found. This is retrieval evidence only "
            "and is not a legal conclusion."
        )

    else:

        status = "WEAK"

        message = (
            "Some domain-specific evidence was found, "
            "but manual verification is required."
        )

    return {

        "status":
            status,

        "message":
            message,

        "domains":
            domains,

        "supported_domains":
            supported_domains,

        "unsupported_domains":
            unsupported_domains,

        "evidence_count":
            len(evidence),

        "strong_evidence_count":
            strong_items,

        "ingredient_evidence_count":
            ingredient_items,

        # FIXED SEMANTICS:
        # This count is now actual textual domain evidence.
        "domain_aligned_count":
            domain_evidence_items,

        "domain_evidence_count":
            domain_evidence_items,

        "domain_evidence":
            domain_summary
    }


# =========================================================
# LLM JSON HELPERS
# =========================================================

def parse_json_object(
    content
):

    if isinstance(
        content,
        dict
    ):

        return content

    if not isinstance(
        content,
        str
    ):

        return None

    content = content.strip()

    try:

        parsed = json.loads(
            content
        )

        if isinstance(
            parsed,
            dict
        ):

            return parsed

    except json.JSONDecodeError:

        pass

    match = re.search(
        r"\{.*\}",
        content,
        flags=re.DOTALL
    )

    if match:

        try:

            parsed = json.loads(
                match.group(
                    0
                )
            )

            if isinstance(
                parsed,
                dict
            ):

                return parsed

        except json.JSONDecodeError:

            pass

    return None


def normalize_llm_analysis(
    data
):

    if not isinstance(
        data,
        dict
    ):

        data = {}

    domain_analysis = data.get(
        "domain_analysis",
        {}
    )

    if not isinstance(
        domain_analysis,
        dict
    ):

        domain_analysis = {}

    risks = data.get(
        "risks",
        []
    )

    if not isinstance(
        risks,
        list
    ):

        risks = [
            str(risks)
        ]

    verification = data.get(
        "recommended_verification",
        []
    )

    if not isinstance(
        verification,
        list
    ):

        verification = [
            str(verification)
        ]

    return {

        "summary":
            str(
                data.get(
                    "summary",
                    "Insufficient evidence."
                )
            ),

        "domain_analysis": {

            "IP":
                str(
                    domain_analysis.get(
                        "IP",
                        "Insufficient evidence."
                    )
                ),

            "TK":
                str(
                    domain_analysis.get(
                        "TK",
                        "Insufficient evidence."
                    )
                ),

            "ABS":
                str(
                    domain_analysis.get(
                        "ABS",
                        "Insufficient evidence."
                    )
                )
        },

        "evidence_interpretation":
            str(
                data.get(
                    "evidence_interpretation",
                    "Insufficient evidence."
                )
            ),

        "risks": [
            str(value)
            for value in risks[:10]
        ],

        "recommended_verification": [
            str(value)
            for value in verification[:10]
        ],

        "limitations":
            str(
                data.get(
                    "limitations",
                    "Insufficient evidence."
                )
            )
    }


# =========================================================
# LLM LEGAL REFERENCE GUARD
# =========================================================

def extract_legal_references(
    text
):

    if not text:
        return set()

    patterns = [

        r"\b[A-Z][A-Za-z ]+\s+Act(?:,\s*\d{4})?",

        r"\bSection\s+\d+[A-Za-z]?\b",

        r"\bSections\s+[\d,\sand-]+\b",

        r"\bRegulation\s+\d+[A-Za-z]?\b",

        r"\bArticle\s+\d+[A-Za-z]?\b",

        r"\bRule\s+\d+[A-Za-z]?\b"
    ]

    matches = set()

    for pattern in patterns:

        for match in re.findall(
            pattern,
            text,
            flags=re.IGNORECASE
        ):

            matches.add(
                normalize_text(
                    match
                )
            )

    return matches


def collect_evidence_legal_references(
    evidence
):

    references = set()

    for item in evidence:

        text = item.get(
            "text",
            ""
        )

        references.update(
            extract_legal_references(
                text
            )
        )

    return references


def sanitize_unsupported_legal_references(
    analysis,
    evidence
):

    if not isinstance(
        analysis,
        dict
    ):

        return analysis

    evidence_refs = (
        collect_evidence_legal_references(
            evidence
        )
    )

    if not evidence_refs:

        evidence_refs = set()

    text_fields = [
        "summary",
        "evidence_interpretation",
        "limitations"
    ]

    for field in text_fields:

        value = analysis.get(
            field,
            ""
        )

        if not isinstance(
            value,
            str
        ):

            continue

        refs = extract_legal_references(
            value
        )

        unsupported = (
            refs - evidence_refs
        )

        if unsupported:

            analysis[field] = (
                "Insufficient evidence. "
                "The model introduced a legal reference "
                "that was not present in the retrieved "
                "evidence."
            )

    risks = analysis.get(
        "risks",
        []
    )

    cleaned_risks = []

    for risk in risks:

        risk = str(
            risk
        )

        refs = extract_legal_references(
            risk
        )

        if refs - evidence_refs:

            cleaned_risks.append(
                "Insufficient evidence."
            )

        else:

            cleaned_risks.append(
                risk
            )

    analysis[
        "risks"
    ] = cleaned_risks[:10]

    verification = analysis.get(
        "recommended_verification",
        []
    )

    cleaned_verification = []

    for recommendation in verification:

        recommendation = str(
            recommendation
        )

        refs = extract_legal_references(
            recommendation
        )

        if refs - evidence_refs:

            cleaned_verification.append(
                "Verify the applicable legal framework "
                "using appropriate authoritative sources."
            )

        else:

            cleaned_verification.append(
                recommendation
            )

    analysis[
        "recommended_verification"
    ] = cleaned_verification[:10]

    return analysis


# =========================================================
# LLM REASONING
# =========================================================

def generate_llm_reasoning(
    product,
    domains,
    evidence,
    validation
):

    if not evidence:

        return {

            "status":
                "NOT_RUN",

            "message":
                (
                    "LLM reasoning was not run because "
                    "no sufficiently relevant evidence "
                    "was retrieved."
                )
        }

    domain_summary = (
        validation.get(
            "domain_evidence",
            {}
        )
    )

    supported_domains = (
        validation.get(
            "supported_domains",
            []
        )
    )

    unsupported_domains = (
        validation.get(
            "unsupported_domains",
            []
        )
    )

    evidence_blocks = []

    for index, item in enumerate(
        evidence[:5],
        start=1
    ):

        evidence_blocks.append(
            f"""
EVIDENCE {index}

Source:
{item.get("source", "Unknown")}

Domain metadata:
{item.get("domain", "UNKNOWN")}

Supported domains from TEXT:
{", ".join(item.get("supported_domains", [])) or "None"}

Retrieval type:
{item.get("retrieval_type", "UNKNOWN")}

Similarity:
{item.get("similarity", "N/A")}

Retrieval score:
{item.get("score", "N/A")}

Evidence quality:
{item.get("evidence_quality", "N/A")}

Page:
{item.get("page", "N/A")}

Chunk:
{item.get("chunk", "N/A")}

Matched terms:
{", ".join(item.get("matched_terms", []))}

Ingredient matches:
{", ".join(item.get("ingredient_matches", []))}

Domain matches:
{json.dumps(item.get("domain_matches", {}))}

Evidence basis:
{", ".join(item.get("evidence_basis", []))}

Evidence text:
{item.get("text", "")}
"""
        )

    evidence_text = "\n".join(
        evidence_blocks
    )

    prompt = f"""
You are the evidence-grounded reasoning engine
for IP-SAKTI.

IP-SAKTI is an Indian IP / Traditional Knowledge /
Access and Benefit Sharing assessment prototype.

You are NOT a lawyer.

Do not provide legal advice.

Do not invent:
- laws
- sections
- regulations
- cases
- government decisions
- databases
- facts
- obligations
- legal mechanisms

=========================================================
ABSOLUTE GROUNDING RULE
=========================================================

You may reason ONLY from:

1. Product information
2. Retrieved evidence below
3. Explicit evidence metadata below

If evidence does not establish something,
say exactly:

"Insufficient evidence."

Do NOT use your general knowledge to fill gaps.

=========================================================
CRITICAL DOMAIN RULE
=========================================================

A document's DOMAIN METADATA is NOT sufficient evidence.

For example:

Domain metadata = IP

does NOT mean:

"IP evidence exists."

IP evidence exists only when the evidence TEXT contains
relevant IP terms shown in "Domain matches".

Likewise:

TK metadata != TK evidence

ABS metadata != ABS evidence

Ingredient match != ABS obligation

Ingredient match != TK evidence

=========================================================
DETECTED DOMAINS
=========================================================

{", ".join(domains)}

Domains with direct evidence:

{", ".join(supported_domains) or "None"}

Domains WITHOUT direct evidence:

{", ".join(unsupported_domains) or "None"}

Domain evidence summary:

{json.dumps(domain_summary, indent=2)}

=========================================================
PRODUCT
=========================================================

Product name:
{product.product_name}

Ingredients:
{", ".join(product.ingredients) or "None provided"}

Purpose:
{product.purpose}

Product type:
{product.product_type}

Jurisdiction:
{product.jurisdiction}

Traditional knowledge answer:
{product.based_on_traditional_knowledge}

=========================================================
RETRIEVED EVIDENCE
=========================================================

{evidence_text}

=========================================================
TASK
=========================================================

Analyze the evidence conservatively.

For EVERY detected domain:

- If that domain has direct evidence, summarize only
  what that evidence supports.

- If that domain has no direct evidence, write:
  "Insufficient evidence."

If only IP evidence exists while TK and ABS are detected,
DO NOT claim that TK or ABS are supported.

If an ingredient appears in evidence, treat that only as
ingredient evidence.

Do NOT infer an ABS obligation solely from an ingredient.

Do NOT infer traditional knowledge solely because something
is herbal, medicinal, indigenous, or an ingredient appears.

Do NOT infer:

- novelty
- patentability
- ownership
- infringement
- compliance
- liability
- legal obligation
- legal violation

unless directly supported by the retrieved evidence.

=========================================================
LEGAL REFERENCE RULE
=========================================================

You MUST NOT name an Act, Section, Regulation, Rule,
Article, case, or other specific legal authority unless
that exact legal reference appears in the retrieved
evidence text.

For example, if the evidence does not contain
"TKDL Act, 2005", you MUST NOT recommend it.

If a legal authority is not present in the evidence,
say:

"Insufficient evidence."

=========================================================
OUTPUT
=========================================================

Return valid JSON with exactly these fields:

{{
  "summary": "...",

  "domain_analysis": {{
    "IP": "...",
    "TK": "...",
    "ABS": "..."
  }},

  "evidence_interpretation": "...",

  "risks": [
    "...",
    "..."
  ],

  "recommended_verification": [
    "...",
    "...",
    "..."
  ],

  "limitations": "..."
}}

=========================================================
FINAL RULE
=========================================================

Evidence is more important than assumptions.

Never convert retrieval signals into legal conclusions.
"""

    try:
        import concurrent.futures

        def _do_chat():
            return ollama.chat(
                model=OLLAMA_MODEL,
                messages=[
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                format="json",
                options={
                    "num_predict": 300,
                    "temperature": 0.2,
                    "num_ctx": 2048,
                }
            )

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_do_chat)
            response = future.result(timeout=4)

        content = (
            response
            .get(
                "message",
                {}
            )
            .get(
                "content",
                ""
            )
        )

        parsed = parse_json_object(
            content
        )

        if parsed is None:

            normalized = normalize_llm_analysis({

                "summary":
                    str(
                        content
                    ),

                "limitations":
                    (
                        "The local model returned "
                        "content that could not be "
                        "parsed as structured JSON."
                    )
            })

            normalized = (
                sanitize_unsupported_legal_references(
                    normalized,
                    evidence
                )
            )

            return {

                "status":
                    "SUCCESS",

                "model":
                    OLLAMA_MODEL,

                "analysis":
                    normalized
            }

        normalized = normalize_llm_analysis(
            parsed
        )

        # SECOND LINE OF DEFENSE:
        # deterministically remove unsupported
        # legal references from model output.
        normalized = (
            sanitize_unsupported_legal_references(
                normalized,
                evidence
            )
        )

        return {

            "status":
                "SUCCESS",

            "model":
                OLLAMA_MODEL,

            "analysis":
                normalized
        }

    except Exception as e:

        logger.exception(
            "Ollama error: %r",
            e
        )

        return {

            "status":
                "ERROR",

            "model":
                OLLAMA_MODEL,

            "message":
                (
                    "Local Ollama model could not be reached. "
                    "Retrieval evidence remains available."
                ),

            "error":
                str(e)
        }


# =========================================================
# CONFIDENCE
# =========================================================

def calculate_confidence(
    evidence,
    validation
):

    # IMPORTANT:
    # This is retrieval/evidence confidence.
    # It is NOT legal confidence.

    if not evidence:

        return {

            "level":
                "LOW",

            "score":
                0.20,

            "basis": [
                "No relevant evidence was retrieved."
            ],

            "warning":
                (
                    "This score does not represent "
                    "legal certainty."
                )
        }

    supported_domains = validation.get(
        "supported_domains",
        []
    )

    strongest = evidence[
        0
    ]

    strongest_score = float(
        strongest.get(
            "score",
            0.0
        )
    )

    similarity = strongest.get(
        "similarity"
    )

    ingredient_match = bool(
        strongest.get(
            "ingredient_matches"
        )
    )

    domain_evidence = bool(
        strongest.get(
            "supported_domains"
        )
    )

    evidence_quality = float(
        strongest.get(
            "evidence_quality",
            0.0
        )
    )

    status = validation.get(
        "status"
    )

    # No domain actually supported.
    if not supported_domains:

        level = "LOW"
        score = 0.20

    # Mixed result:
    # some domains supported, some unsupported.
    elif status == "PARTIAL":

        if (
            strongest_score >= 12
            and domain_evidence
            and evidence_quality >= 0.60
        ):

            level = "MEDIUM"
            score = 0.65

        else:

            level = "LOW"
            score = 0.45

    elif status == "UNSUPPORTED":

        level = "LOW"
        score = 0.25

    elif (
        strongest_score >= 12
        and domain_evidence
        and ingredient_match
        and evidence_quality >= 0.60
    ):

        level = "HIGH"
        score = 0.85

    elif (
        strongest_score >= 8
        and domain_evidence
        and evidence_quality >= 0.40
    ):

        level = "MEDIUM"
        score = 0.70

    elif (
        similarity is not None
        and float(
            similarity or 0.0
        ) >= 0.75
        and domain_evidence
        and evidence_quality >= 0.35
    ):

        level = "MEDIUM"
        score = 0.65

    else:

        level = "LOW"
        score = 0.45

    basis = []

    if strongest.get(
        "domain"
    ) in supported_domains:

        basis.append(
            "domain-specific textual evidence"
        )

    if ingredient_match:

        basis.append(
            "ingredient evidence"
        )

    if similarity is not None:

        basis.append(
            "semantic retrieval"
        )

    if strongest.get(
        "matched_terms"
    ):

        basis.append(
            "keyword overlap"
        )

    if validation.get(
        "status"
    ) == "PARTIAL":

        basis.append(
            "partial domain coverage"
        )

    return {

        "level":
            level,

        "score":
            score,

        "basis":
            basis,

        "supported_domains":
            supported_domains,

        "warning":
            (
                "This is retrieval/evidence confidence, "
                "not legal certainty."
            )
    }


# =========================================================
# ACTION PLAN
# =========================================================

def build_action_plan(
    domains,
    evidence,
    validation
):

    actions = []

    status = validation.get(
        "status"
    )

    supported_domains = validation.get(
        "supported_domains",
        []
    )

    unsupported_domains = validation.get(
        "unsupported_domains",
        []
    )

    if status == "UNSUPPORTED":

        actions.append(
            "Do not rely on an unsupported conclusion."
        )

        actions.append(
            "Expand the authoritative corpus with "
            "relevant TK/ABS/IP source material."
        )

    elif status == "PARTIAL":

        actions.append(
            "Use only the supported-domain evidence "
            "for interpretation."
        )

        actions.append(
            "Do not infer conclusions for unsupported "
            "domains."
        )

        actions.append(
            "Expand or verify the corpus for: "
            + ", ".join(
                unsupported_domains
            )
        )

    else:

        actions.append(
            "Open and review the original retrieved "
            "source documents."
        )

        actions.append(
            "Compare the LLM interpretation with "
            "the underlying evidence."
        )

    if "TK" in domains:

        if "TK" in supported_domains:

            actions.append(
                "Verify the retrieved traditional-knowledge "
                "evidence against the original source."
            )

        else:

            actions.append(
                "No direct TK evidence was established. "
                "Verify whether the ingredients, formulation, "
                "or stated use are actually associated with "
                "documented traditional knowledge."
            )

    if "ABS" in domains:

        if "ABS" in supported_domains:

            actions.append(
                "Verify the retrieved biological-resource "
                "and access/benefit-sharing evidence using "
                "authoritative sources."
            )

        else:

            actions.append(
                "No direct ABS evidence was established. "
                "An ingredient match alone is not sufficient."
            )

    if "IP" in domains:

        if "IP" in supported_domains:

            actions.append(
                "Identify the specific IP issue supported "
                "by the retrieved evidence before drawing "
                "a conclusion."
            )

        else:

            actions.append(
                "No direct IP evidence was established. "
                "Verify the relevant IP question separately."
            )

    actions.append(
        "Verify material conclusions with an "
        "appropriate IP/TK/ABS facilitator or "
        "qualified professional."
    )

    return actions


# =========================================================
# RESPONSE SANITIZATION
# =========================================================

def sanitize_evidence(
    evidence
):

    output = []

    for item in evidence:

        output.append({

            "id":
                item.get(
                    "id"
                ),

            "domain":
                item.get(
                    "domain"
                ),

            "source":
                item.get(
                    "source"
                ),

            "page":
                item.get(
                    "page"
                ),

            "chunk":
                item.get(
                    "chunk"
                ),

            "retrieval_type":
                item.get(
                    "retrieval_type"
                ),

            "similarity":
                item.get(
                    "similarity"
                ),

            "score":
                item.get(
                    "score"
                ),

            "evidence_quality":
                item.get(
                    "evidence_quality"
                ),

            "evidence_basis":
                item.get(
                    "evidence_basis",
                    []
                ),

            "matched_terms":
                item.get(
                    "matched_terms",
                    []
                ),

            "ingredient_matches":
                item.get(
                    "ingredient_matches",
                    []
                ),

            "domain_matches":
                item.get(
                    "domain_matches",
                    {}
                ),

            # NEW
            "supported_domains":
                item.get(
                    "supported_domains",
                    []
                ),

            "text":
                item.get(
                    "text",
                    ""
                )
        })

    return output



# =========================================================
# MVP ENHANCEMENT LAYER
# =========================================================
#
# This section extends the original 4K+ line backend without
# removing or replacing the existing retrieval / validation /
# Ollama reasoning pipeline.
#
# Added for the Streamlit MVP:
#   - deterministic product classification
#   - explicit domain-routing summary
#   - missing-information detection
#   - safe-decision / abstention state
#   - human-escalation recommendation
#   - source/citation records
#   - Bhashini-compatible translation service
#   - analysis translation endpoint
#
# Translation is optional. If Bhashini credentials/configuration
# are absent or the service fails, the original English content
# is returned unchanged so assessment never breaks.
# =========================================================

from typing import Any, Dict
import urllib.request
import urllib.error


# ---------------------------------------------------------
# BHASHINI CONFIGURATION
# ---------------------------------------------------------

BHASHINI_ENABLED = os.getenv(
    "BHASHINI_ENABLED",
    "false"
).strip().lower() in {
    "1", "true", "yes", "y", "on"
}

BHASHINI_API_URL = os.getenv(
    "BHASHINI_API_URL",
    "https://dhruva-api.bhashini.gov.in/services/inference/pipeline"
).strip()

BHASHINI_API_KEY = os.getenv(
    "BHASHINI_API_KEY",
    ""
).strip()

BHASHINI_USER_ID = os.getenv(
    "BHASHINI_USER_ID",
    ""
).strip()

BHASHINI_PIPELINE_ID = os.getenv(
    "BHASHINI_PIPELINE_ID",
    ""
).strip()

BHASHINI_TIMEOUT = max(
    5,
    int(
        os.getenv(
            "BHASHINI_TIMEOUT",
            "20"
        )
    )
)

CANONICAL_LANGUAGE = "en"

SUPPORTED_LANGUAGES = {
    "en": "English",
    "hi": "Hindi",
    "mr": "Marathi",
}


def normalize_language_code(language):
    """
    Normalize common language names/codes into the compact
    language codes used by the frontend.
    """
    value = str(
        language or ""
    ).strip().lower()

    aliases = {
        "english": "en",
        "en-us": "en",
        "en_in": "en",
        "en-in": "en",
        "hindi": "hi",
        "hi-in": "hi",
        "marathi": "mr",
        "mr-in": "mr",
    }

    value = aliases.get(
        value,
        value
    )

    if value not in SUPPORTED_LANGUAGES:
        return CANONICAL_LANGUAGE

    return value


def _bhashini_request(payload):
    """
    Low-level Bhashini request helper.

    The exact pipeline configuration can vary by Bhashini
    deployment. It is therefore controlled through environment
    variables instead of hard-coded credentials/models.
    """
    if not BHASHINI_ENABLED:
        raise RuntimeError(
            "Bhashini translation is disabled."
        )

    if not BHASHINI_API_URL:
        raise RuntimeError(
            "BHASHINI_API_URL is not configured."
        )

    data = json.dumps(
        payload
    ).encode(
        "utf-8"
    )

    headers = {
        "Content-Type":
            "application/json"
    }

    if BHASHINI_API_KEY:
        headers[
            "ulcaApiKey"
        ] = BHASHINI_API_KEY

    if BHASHINI_USER_ID:
        headers[
            "userID"
        ] = BHASHINI_USER_ID

    request = urllib.request.Request(
        BHASHINI_API_URL,
        data=data,
        headers=headers,
        method="POST"
    )

    try:
        with urllib.request.urlopen(
            request,
            timeout=BHASHINI_TIMEOUT
        ) as response:

            raw = response.read().decode(
                "utf-8"
            )

            return json.loads(
                raw
            )

    except urllib.error.HTTPError as e:

        body = ""

        try:
            body = e.read().decode(
                "utf-8",
                errors="ignore"
            )
        except Exception:
            pass

        raise RuntimeError(
            f"Bhashini HTTP {e.code}: {body[:500]}"
        ) from e

    except urllib.error.URLError as e:

        raise RuntimeError(
            f"Bhashini connection failed: {e}"
        ) from e


def _extract_translation_text(response):
    """
    Best-effort extraction across common Bhashini inference
    response shapes.
    """
    if response is None:
        return ""

    if isinstance(
        response,
        str
    ):
        return response.strip()

    if isinstance(
        response,
        list
    ):

        for item in response:

            value = _extract_translation_text(
                item
            )

            if value:
                return value

        return ""

    if not isinstance(
        response,
        dict
    ):
        return ""

    # Common direct keys.
    for key in (
        "translatedText",
        "translated_text",
        "translation",
        "text",
        "output",
        "generated_text",
    ):

        value = response.get(
            key
        )

        if isinstance(
            value,
            str
        ) and value.strip():

            return value.strip()

    # Common nested Bhashini shapes.
    for key in (
        "pipelineResponse",
        "pipeline_response",
        "response",
        "data",
        "result",
        "outputs",
        "output"
    ):

        value = response.get(
            key
        )

        if value is None:
            continue

        extracted = _extract_translation_text(
            value
        )

        if extracted:
            return extracted

    return ""


def translate_text(
    text,
    source_lang="en",
    target_lang="en"
):
    """
    Translate a single string.

    Failure-safe by design: the original text is returned when
    Bhashini is unavailable, disabled, or returns no translation.
    """
    if text is None:
        return ""

    text = str(
        text
    )

    source_lang = normalize_language_code(
        source_lang
    )

    target_lang = normalize_language_code(
        target_lang
    )

    if (
        not text.strip()
        or source_lang == target_lang
    ):
        return text

    # Generic Bhashini/ULCA pipeline payload.
    payload = {
        "pipelineTasks": [
            {
                "taskType": "translation",
                "config": {
                    "language": {
                        "sourceLanguage":
                            source_lang,
                        "targetLanguage":
                            target_lang
                    },
                    "serviceId":
                        os.getenv(
                            "BHASHINI_TRANSLATION_SERVICE_ID",
                            ""
                        )
                }
            }
        ],
        "inputData": {
            "input": [
                {
                    "source":
                        text
                }
            ]
        }
    }

    if BHASHINI_PIPELINE_ID:
        payload[
            "pipelineId"
        ] = BHASHINI_PIPELINE_ID

    try:

        response = _bhashini_request(
            payload
        )

        translated = _extract_translation_text(
            response
        )

        if translated:
            return translated

        logger.warning(
            "Bhashini returned no translation."
        )

    except Exception as e:

        logger.warning(
            "Translation fallback: %r",
            e
        )

    return text


def _translate_value(
    value,
    target_lang,
    source_lang="en"
):
    """
    Recursively translate narrative strings while preserving
    numbers, IDs, URLs and structural JSON.
    """
    if isinstance(
        value,
        str
    ):

        # Preserve URLs and obvious source identifiers.
        if (
            value.startswith("http://")
            or value.startswith("https://")
        ):
            return value

        return translate_text(
            value,
            source_lang,
            target_lang
        )

    if isinstance(
        value,
        list
    ):

        return [
            _translate_value(
                item,
                target_lang,
                source_lang
            )
            for item in value
        ]

    if isinstance(
        value,
        dict
    ):

        translated = {}

        # Evidence/source fields remain attached to their
        # original source and are intentionally not translated.
        protected_keys = {
            "id",
            "source",
            "url",
            "source_url",
            "citation",
            "page",
            "chunk",
            "similarity",
            "score",
            "evidence_quality",
            "retrieval_type",
            "embedding_model",
            "matched_terms",
            "ingredient_matches",
            "domain_matches",
            "supported_domains",
            "unsupported_domains",
            "domains",
            "domain",
        }

        for key, item in value.items():

            if key in protected_keys:

                translated[key] = item

            else:

                translated[key] = _translate_value(
                    item,
                    target_lang,
                    source_lang
                )

        return translated

    return value


def translate_analysis_object(
    analysis,
    target_lang,
    source_lang="en"
):
    """
    Translate the analysis response for UI display while
    retaining source identifiers/citations in their original form.
    """
    target_lang = normalize_language_code(
        target_lang
    )

    source_lang = normalize_language_code(
        source_lang
    )

    if (
        target_lang == source_lang
        or not isinstance(
            analysis,
            (dict, list)
        )
    ):
        return analysis

    return _translate_value(
        analysis,
        target_lang,
        source_lang
    )


# ---------------------------------------------------------
# TRANSLATION REQUEST MODELS
# ---------------------------------------------------------

class TranslationInput(BaseModel):

    text: str = Field(
        ...,
        min_length=1,
        max_length=10000
    )

    source_lang: str = Field(
        default="en",
        max_length=20
    )

    target_lang: str = Field(
        default="hi",
        max_length=20
    )


class AnalysisTranslationInput(BaseModel):

    analysis: Dict[str, Any]

    target_lang: str = Field(
        default="hi",
        max_length=20
    )

    source_lang: str = Field(
        default="en",
        max_length=20
    )


# ---------------------------------------------------------
# ENHANCED PRODUCT CLASSIFICATION
# ---------------------------------------------------------

def classify_product_v2(
    product
):
    """
    Deterministic MVP classification.

    This is intentionally a routing/classification aid, not
    a legal determination. It supplements the original
    classify_product() function rather than replacing it.
    """
    product_type = normalize_text(
        product.product_type
    )

    purpose = normalize_text(
        product.purpose
    )

    combined = " ".join([
        product_type,
        purpose,
        normalize_text(
            product.product_name
        )
    ])

    if any(
        phrase_in_text(
            combined,
            term
        )
        for term in (
            "cosmetic",
            "cream",
            "lotion",
            "serum",
            "shampoo",
            "soap",
            "skin care",
            "hair care"
        )
    ):

        category = "Cosmetic"

    elif any(
        phrase_in_text(
            combined,
            term
        )
        for term in (
            "classical medicine",
            "classical ayurvedic",
            "ayurvedic medicine",
            "traditional medicine"
        )
    ):

        category = "Classical Medicine"

    elif any(
        phrase_in_text(
            combined,
            term
        )
        for term in (
            "proprietary medicine",
            "proprietary",
            "patent medicine"
        )
    ):

        category = "Proprietary Medicine"

    elif any(
        phrase_in_text(
            combined,
            term
        )
        for term in (
            "new drug",
            "novel drug",
            "new pharmaceutical"
        )
    ):

        category = "New Drug"

    elif any(
        phrase_in_text(
            combined,
            term
        )
        for term in (
            "phytopharmaceutical",
            "phytopharma"
        )
    ):

        category = "Phytopharmaceutical"

    elif any(
        phrase_in_text(
            combined,
            term
        )
        for term in (
            "food",
            "beverage",
            "aahar",
            "ayurveda aahar"
        )
    ) and (
        "ayur" in combined
        or "aahar" in combined
    ):

        category = "Ayurveda-Aahar"

    else:

        category = (
            product.product_type
            or "Unspecified"
        )

    return {

        "category":
            category,

        "input_product_type":
            product.product_type,

        "purpose":
            product.purpose,

        "traditional_knowledge":
            product.based_on_traditional_knowledge,

        "jurisdiction":
            product.jurisdiction,

        "classification_basis": [
            "User-provided product type",
            "User-provided purpose",
            "Deterministic MVP keyword routing"
        ],

        "note": (
            "This is a prototype classification and "
            "routing signal, not a legal or regulatory "
            "determination."
        )
    }


# ---------------------------------------------------------
# ENHANCED DOMAIN ROUTING
# ---------------------------------------------------------

def build_domain_routing_summary(
    product,
    domains,
    validation=None
):
    validation = validation or {}

    supported = validation.get(
        "supported_domains",
        []
    )

    unsupported = validation.get(
        "unsupported_domains",
        []
    )

    routing = []

    for domain in domains:

        if domain == "IP":

            label = "Intellectual Property"

            reason = (
                "Baseline IP assessment is enabled for "
                "the product."
            )

        elif domain == "TK":

            label = "Traditional Knowledge"

            reason = (
                "Traditional-knowledge signals were detected "
                "from the product information."
            )

        elif domain == "ABS":

            label = "Access and Benefit Sharing"

            reason = (
                "Biological-resource / biodiversity signals "
                "were detected. This is a routing signal only."
            )

        else:

            label = str(
                domain
            )

            reason = (
                "Domain detected by the prototype router."
            )

        routing.append({

            "domain":
                domain,

            "label":
                label,

            "detected":
                True,

            "direct_evidence_supported":
                domain in supported,

            "evidence_status":
                (
                    "SUPPORTED"
                    if domain in supported
                    else "NOT_ESTABLISHED"
                ),

            "reason":
                reason
        })

    return {

        "detected_domains":
            domains,

        "supported_domains":
            supported,

        "unsupported_domains":
            unsupported,

        "routing":
            routing,

        "note": (
            "Domain routing identifies areas for review. "
            "It does not establish legal applicability."
        )
    }


# ---------------------------------------------------------
# MISSING INFORMATION
# ---------------------------------------------------------

def identify_missing_information(
    product,
    domains,
    validation,
    evidence
):
    """
    Identify information gaps that materially affect the MVP
    assessment. These are intentionally conservative.
    """
    missing = []

    if not product.ingredients:

        missing.append(
            "Complete ingredient/component list."
        )

    if not str(
        product.purpose
    ).strip():

        missing.append(
            "Specific intended use or purpose."
        )

    if not str(
        product.product_type
    ).strip():

        missing.append(
            "Product category/type."
        )

    jurisdiction = normalize_text(
        product.jurisdiction
    )

    if not jurisdiction:

        missing.append(
            "Applicable jurisdiction."
        )

    tk_value = normalize_text(
        product.based_on_traditional_knowledge
    )

    if tk_value in {
        "",
        "unknown",
        "not known",
        "not sure",
        "unsure"
    }:

        if "TK" in domains:

            missing.append(
                "Whether the product/formulation/use is "
                "based on documented traditional knowledge."
            )

    if "TK" in domains:

        if "TK" not in validation.get(
            "supported_domains",
            []
        ):

            missing.append(
                "Authoritative evidence linking the stated "
                "ingredient/formulation/use to traditional knowledge."
            )

    if "ABS" in domains:

        if "ABS" not in validation.get(
            "supported_domains",
            []
        ):

            missing.append(
                "Evidence establishing the relevant biological "
                "or genetic resource and applicable ABS context."
            )

    if "IP" in domains:

        if "IP" not in validation.get(
            "supported_domains",
            []
        ):

            missing.append(
                "Specific IP question to investigate, such as "
                "patent, trademark, design, copyright, novelty "
                "or prior-art relevance."
            )

    if not evidence:

        missing.append(
            "Relevant authoritative corpus evidence."
        )

    # Stable order + de-duplication.
    result = []

    seen = set()

    for item in missing:

        key = normalize_text(
            item
        )

        if key and key not in seen:

            result.append(
                item
            )

            seen.add(
                key
            )

    return result[:15]


# ---------------------------------------------------------
# SOURCE / CITATION RECORDS
# ---------------------------------------------------------

def _extract_url_from_value(
    value
):
    if not isinstance(
        value,
        str
    ):
        return ""

    match = re.search(
        r"https?://[^\s<>\"]+",
        value
    )

    if not match:
        return ""

    return match.group(
        0
    ).rstrip(
        ".,);]"
    )


def get_document_url(
    item
):
    """
    Return a URL only when one is actually present in corpus
    metadata/source fields. Never fabricate a citation URL.
    """
    metadata = item.get(
        "metadata",
        {}
    ) or {}

    candidates = [
        item.get(
            "url"
        ),
        item.get(
            "source_url"
        ),
        item.get(
            "citation_url"
        ),
        metadata.get(
            "url"
        ),
        metadata.get(
            "source_url"
        ),
        metadata.get(
            "citation_url"
        ),
        item.get(
            "citation"
        ),
        item.get(
            "source"
        ),
    ]

    for value in candidates:

        url = _extract_url_from_value(
            value
        )

        if url:
            return url

    return ""


def build_source_records(
    evidence
):
    sources = []

    seen = set()

    for item in evidence:

        source = str(
            item.get(
                "source",
                "Unknown source"
            )
        ).strip()

        page = item.get(
            "page"
        )

        url = get_document_url(
            item
        )

        key = (
            source,
            page,
            url
        )

        if key in seen:
            continue

        seen.add(
            key
        )

        record = {

            "source":
                source,

            "page":
                page,

            "chunk":
                item.get(
                    "chunk"
                ),

            "domain":
                item.get(
                    "domain"
                ),

            "url":
                url or None,

            "citation":
                (
                    f"{source}"
                    + (
                        f", page {page}"
                        if page is not None
                        else ""
                    )
                ),

            "evidence_id":
                item.get(
                    "id"
                )
        }

        sources.append(
            record
        )

    return sources


# ---------------------------------------------------------
# SAFE DECISION
# ---------------------------------------------------------

def build_safe_decision(
    domains,
    evidence,
    validation,
    confidence,
    missing_information
):
    status = validation.get(
        "status",
        "UNSUPPORTED"
    )

    confidence_level = (
        confidence or {}
    ).get(
        "level",
        "LOW"
    )

    supported = validation.get(
        "supported_domains",
        []
    )

    unsupported = validation.get(
        "unsupported_domains",
        []
    )

    if not evidence:

        return {

            "decision":
                "ABSTAIN",

            "status":
                "UNSUPPORTED",

            "safe":
                True,

            "reason": (
                "No sufficiently relevant evidence was "
                "retrieved. The system will not infer a "
                "legal or compliance conclusion."
            ),

            "next_step": (
                "Add or retrieve authoritative evidence "
                "and repeat the assessment."
            )
        }

    if status in {
        "UNSUPPORTED",
        "PARTIAL"
    }:

        return {

            "decision":
                "HUMAN_VERIFICATION_REQUIRED",

            "status":
                status,

            "safe":
                True,

            "reason": (
                "The available evidence does not establish "
                "all detected domains."
            ),

            "next_step": (
                "Verify unsupported domains and the original "
                "source documents before making a decision."
            ),

            "supported_domains":
                supported,

            "unsupported_domains":
                unsupported
        }

    if (
        confidence_level == "HIGH"
        and not missing_information
    ):

        return {

            "decision":
                "PROCEED_TO_VERIFICATION",

            "status":
                "EVIDENCE_FOUND",

            "safe":
                True,

            "reason": (
                "Relevant evidence was retrieved with high "
                "retrieval confidence, but the result is "
                "still not a legal determination."
            ),

            "next_step": (
                "Review the original evidence and obtain "
                "appropriate professional verification."
            )
        }

    return {

        "decision":
            "VERIFY_BEFORE_ACTION",

        "status":
            status,

        "safe":
            True,

        "reason": (
            "Evidence was retrieved, but the available "
            "information is not sufficient for an autonomous "
            "legal/compliance decision."
        ),

        "next_step": (
            "Review evidence, fill missing information, "
            "and obtain human verification."
        )
    }


# ---------------------------------------------------------
# HUMAN ESCALATION
# ---------------------------------------------------------

def build_human_escalation(
    domains,
    validation,
    confidence,
    missing_information
):
    status = validation.get(
        "status",
        "UNSUPPORTED"
    )

    confidence_level = (
        confidence or {}
    ).get(
        "level",
        "LOW"
    )

    unsupported = validation.get(
        "unsupported_domains",
        []
    )

    recommended = bool(
        missing_information
        or unsupported
        or status in {
            "UNSUPPORTED",
            "PARTIAL",
            "WEAK"
        }
        or confidence_level == "LOW"
    )

    if "ABS" in domains:

        reviewer = (
            "IP/TK/ABS facilitator or qualified "
            "biodiversity/ABS professional"
        )

    elif "TK" in domains:

        reviewer = (
            "IP/TK facilitator or qualified "
            "traditional-knowledge professional"
        )

    else:

        reviewer = (
            "Appropriate IP professional or qualified reviewer"
        )

    reasons = []

    if unsupported:

        reasons.append(
            "direct evidence is missing for: "
            + ", ".join(
                unsupported
            )
        )

    if missing_information:

        reasons.append(
            "important information is missing"
        )

    if confidence_level == "LOW":

        reasons.append(
            "retrieval/evidence confidence is low"
        )

    if not reasons:

        reasons.append(
            "material conclusions should be independently verified"
        )

    return {

        "recommended":
            recommended,

        "reason":
            "; ".join(
                reasons
            ),

        "suggested_reviewer":
            reviewer,

        "domains":
            domains
    }


# ---------------------------------------------------------
# TRANSLATION ENDPOINTS
# ---------------------------------------------------------

@app.post(
    "/api/language/translate"
)
def language_translate(
    request: TranslationInput
):
    source_lang = normalize_language_code(
        request.source_lang
    )

    target_lang = normalize_language_code(
        request.target_lang
    )

    translated = translate_text(
        request.text,
        source_lang,
        target_lang
    )

    return {

        "text":
            translated,

        "source_lang":
            source_lang,

        "target_lang":
            target_lang,

        "provider":
            (
                "bhashini"
                if BHASHINI_ENABLED
                else "fallback"
            ),

        "translated":
            translated != request.text
    }


@app.post(
    "/api/language/translate-analysis"
)
def language_translate_analysis(
    request: AnalysisTranslationInput
):
    source_lang = normalize_language_code(
        request.source_lang
    )

    target_lang = normalize_language_code(
        request.target_lang
    )

    translated = translate_analysis_object(
        request.analysis,
        target_lang,
        source_lang
    )

    return translated


@app.get(
    "/api/language"
)
def language_status():
    return {

        "enabled":
            BHASHINI_ENABLED,

        "provider":
            "Bhashini"
            if BHASHINI_ENABLED
            else "fallback",

        "supported_languages":
            SUPPORTED_LANGUAGES,

        "canonical_language":
            CANONICAL_LANGUAGE
    }




# =========================================================
# AGENTIC AI CHAT — EXISTING IP-SAKTI TOOL WIRING
# =========================================================
# run_agent_chat() (defined below, near /api/agent/chat) calls
# search_corpus(), validate_evidence(), generate_llm_reasoning(),
# calculate_confidence(), build_source_records(),
# identify_missing_information(), build_human_escalation() and
# _run_agentic_stage() directly — they are already in this module's
# scope, so no separate tool-registration step is needed.

# =========================================================
# OPTIONAL AGENTIC AI RESEARCH LAYER (ADDITIVE / FAIL-SAFE)
# =========================================================
# This layer is embedded in this single-file main.py so the project can run
# without requiring a separate services/agentic_ai package. Existing IP-SAKTI
# retrieval, validation, reasoning, confidence, action plan and endpoints are
# preserved. External web content is untrusted and is never treated as legal
# advice. API credentials are read only from environment variables.

TIER1_DOMAINS = {
    "ipindia.gov.in", "cgpdtm.gov.in", "indiacode.nic.in", "egazette.nic.in",
    "ayush.gov.in", "fssai.gov.in", "nbaindia.org", "plantauthority.gov.in",
    "dbtindia.gov.in", "moef.gov.in", "wipo.int", "wto.org", "cbd.int",
    "un.org", "who.int", "fao.org", "treaties.un.org",
}

TIER1_SUFFIXES = (".gov.in", ".nic.in", ".gov", ".int")
TIER2_HINTS = (".ac.in", ".edu", ".ac.uk", "university", "institute", "research")
TIER3_HINTS = ("law", "legal", "ipfirm", "consult", "solicitor", "attorney")


def _hostname(url: str) -> str:
    try:
        return (urlparse(str(url)).hostname or "").lower().strip(".")
    except Exception:
        return ""


def validate_url(url: str) -> bool:
    """Allow only normal HTTP(S) URLs; web content is treated as untrusted input."""
    try:
        value = str(url or "").strip()
        parsed = urlparse(value)
        return (
            len(value) <= 2048
            and parsed.scheme in {"http", "https"}
            and bool(parsed.hostname)
            and "@" not in (parsed.netloc or "")
        )
    except Exception:
        return False


def authority_for_url(url: str) -> Dict[str, Any]:
    host = _hostname(url)
    if not host:
        return {"tier": 4, "label": "Invalid / unknown", "score": 0.0}
    if host in TIER1_DOMAINS or any(host.endswith(suffix) for suffix in TIER1_SUFFIXES):
        return {"tier": 1, "label": "TIER_1", "score": 1.0}
    if any(hint in host for hint in TIER2_HINTS):
        return {"tier": 2, "label": "TIER_2", "score": 0.8}
    if any(hint in host for hint in TIER3_HINTS):
        return {"tier": 3, "label": "TIER_3", "score": 0.55}
    return {"tier": 4, "label": "TIER_4", "score": 0.2}


def _parse_date(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        text = str(value).strip().replace("Z", "+00:00")
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _recency_score(value: Any) -> float:
    dt = _parse_date(value)
    if dt is None:
        return 0.45
    age_days = max(0, (datetime.now(timezone.utc) - dt.astimezone(timezone.utc)).days)
    return round(max(0.25, 1.0 - min(age_days, 3650) / 5000), 3)


def _tokenize(text: str) -> set[str]:
    import re
    return set(re.findall(r"[a-z0-9]{4,}", str(text or "").lower()))


def validate_source(result: Dict[str, Any], query: str = "", domain: str = "") -> Dict[str, Any]:
    """Convert one provider result into traceable, conservative evidence metadata."""
    url = str(result.get("url", "")).strip()
    url_valid = validate_url(url)
    authority = authority_for_url(url) if url_valid else {"tier": 4, "label": "TIER_4", "score": 0.0}

    title = str(result.get("title", "")).strip()
    evidence_text = str(result.get("content") or result.get("snippet") or result.get("evidence_text") or "").strip()
    searchable = _tokenize(f"{title} {evidence_text}")
    query_tokens = _tokenize(query)
    overlap = len(searchable & query_tokens) / max(len(query_tokens), 1)
    domain_signal = 1.0 if domain and domain.lower() in f"{title} {evidence_text}".lower() else 0.0
    relevance = round(min(1.0, 0.75 * overlap + 0.25 * domain_signal), 3)

    published = result.get("published_at") or result.get("publication_date")
    updated = result.get("updated_at") or result.get("last_updated")
    date_for_score = updated or published
    confidence = round(
        0.55 * authority["score"] +
        0.30 * relevance +
        0.15 * _recency_score(date_for_score),
        3,
    )

    validated = bool(
        url_valid
        and evidence_text
        and confidence >= 0.35
        and authority["tier"] <= 3
    )

    citation = title if title else "Verified web source"
    if url_valid:
        citation = f"{citation} — {url}"

    return {
        "source": title or url or "Unknown web source",
        "title": title,
        "url": url,
        "domain": str(result.get("domain") or domain or "UNKNOWN").upper(),
        "authority_level": authority["label"],
        "authority_tier": authority["tier"],
        "publication_date": published,
        "last_updated": updated,
        "relevance_score": relevance,
        "confidence": confidence,
        "evidence_text": evidence_text,
        "citation": citation,
        "url_valid": url_valid,
        "validated": validated,
        "validation_note": (
            "Authoritative source suitable for evidence support."
            if authority["tier"] == 1
            else "Secondary source; verify against a Tier 1 source before consequential use."
        ),
        "agent": result.get("agent"),
        "research_question": result.get("research_question"),
    }


def validate_sources(results: Iterable[Dict[str, Any]], query: str = "", domain: str = "") -> List[Dict[str, Any]]:
    validated = [validate_source(item, query=query, domain=domain) for item in results]
    return sorted(
        validated,
        key=lambda item: (
            bool(item.get("validated")),
            -int(item.get("authority_tier", 4)),
            float(item.get("confidence", 0.0)),
            float(item.get("relevance_score", 0.0)),
        ),
        reverse=True,
    )

DEFAULT_OFFICIAL_DOMAINS = [
    "ipindia.gov.in", "cgpdtm.gov.in", "indiacode.nic.in", "egazette.nic.in",
    "ayush.gov.in", "fssai.gov.in", "nbaindia.org", "plantauthority.gov.in",
    "wipo.int", "wto.org", "cbd.int", "un.org",
]

TOPIC_BY_DOMAIN = {
    "IP": "patents patentability Section 3(p) geographical indications trademarks copyright designs plant variety protection Indian IP rules WIPO TRIPS PCT Madrid Hague Budapest",
    "TK": "traditional knowledge TKDL prior art traditional formulations community knowledge Section 3(p) WIPO traditional knowledge treaty",
    "ABS": "biological resources access benefit sharing Biological Diversity Act rules regulations National Biodiversity Authority Nagoya Protocol CBD",
    "REGULATORY": "AYUSH FSSAI Ayurveda-Aahar Drugs and Cosmetics Rules official notifications amendments regulatory classification",
}


def _post_json(url: str, payload: Dict[str, Any], timeout: int) -> Dict[str, Any]:
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def search_web(
    query: str,
    *,
    domains: List[str] | None = None,
    max_results: int = 5,
    timeout: int = 15,
) -> Dict[str, Any]:
    """Search Tavily when configured; otherwise fail closed without breaking IP-SAKTI."""
    query = str(query or "").strip()[:1800]
    if not query:
        return {"status": "NO_QUERY", "provider": None, "query": "", "results": []}

    api_key = os.getenv("TAVILY_API_KEY", "").strip()
    if not api_key:
        return {
            "status": "DISABLED",
            "provider": None,
            "query": query,
            "results": [],
            "reason": "TAVILY_API_KEY is not configured.",
        }

    payload: Dict[str, Any] = {
        "api_key": api_key,
        "query": query,
        "search_depth": os.getenv("AGENTIC_SEARCH_DEPTH", "advanced"),
        "max_results": max(1, min(int(max_results), 10)),
        "include_answer": False,
        "include_raw_content": False,
    }
    clean_domains = [str(x).strip() for x in (domains or []) if str(x).strip()]
    if clean_domains:
        payload["include_domains"] = clean_domains

    try:
        data = _post_json("https://api.tavily.com/search", payload, timeout)
        results = []
        for item in data.get("results", []) or []:
            if not isinstance(item, dict):
                continue
            results.append({
                "title": str(item.get("title", "")),
                "url": str(item.get("url", "")),
                "content": str(item.get("content", "")),
                "published_at": item.get("published_date"),
            })
        return {"status": "SUCCESS", "provider": "tavily", "query": query, "results": results}
    except (HTTPError, URLError, TimeoutError, ValueError) as exc:
        return {
            "status": "ERROR",
            "provider": "tavily",
            "query": query,
            "results": [],
            "error": type(exc).__name__,
        }
    except Exception as exc:
        return {
            "status": "ERROR",
            "provider": "tavily",
            "query": query,
            "results": [],
            "error": type(exc).__name__,
        }


def build_targeted_queries(product: Dict[str, Any], domains: List[str]) -> List[Dict[str, Any]]:
    """Create small, domain-specific research tasks instead of one broad web query."""
    name = str(product.get("product_name", "")).strip()
    ingredients = ", ".join(str(x) for x in product.get("ingredients", [])[:20])
    purpose = str(product.get("purpose", "")).strip()
    jurisdiction = str(product.get("jurisdiction", "India")).strip()
    context = f"Product: {name}; Ingredients: {ingredients or 'none provided'}; Purpose: {purpose}; Jurisdiction: {jurisdiction}"

    tasks = []
    selected = [str(d).upper() for d in domains if str(d).strip()]
    if not selected:
        selected = ["IP"]
    for domain in selected:
        topic = TOPIC_BY_DOMAIN.get(domain, TOPIC_BY_DOMAIN["REGULATORY"])
        tasks.append({
            "agent": f"{domain} Research Agent",
            "domain": domain,
            "query": f"{context}. Find current authoritative sources about {topic}. Prefer official legislation, registries, government guidance and treaty sources.",
        })
    tasks.append({
        "agent": "Web Research Agent",
        "domain": "REGULATORY",
        "query": f"{context}. Find current authoritative laws, rules, notifications, amendments or regulator guidance relevant to the product classification and stated claims.",
    })
    return tasks

def build_research_plan(
    product: Dict[str, Any],
    existing_evidence: List[Dict[str, Any]],
    validation: Dict[str, Any],
) -> Dict[str, Any]:
    jurisdiction = str(product.get("jurisdiction", "India")).strip()
    domains = [str(x).upper() for x in validation.get("domains") or []]
    supported = {str(x).upper() for x in validation.get("supported_domains") or []}
    unsupported = {str(x).upper() for x in validation.get("unsupported_domains") or []}
    tk_value = str(product.get("based_on_traditional_knowledge", "unknown")).lower().strip()

    if not domains:
        domains = ["IP"]

    tasks: List[Dict[str, Any]] = []
    for domain in domains:
        should_research = domain in unsupported or not existing_evidence
        if domain == "TK" and tk_value in {"yes", "true", "1", "y"}:
            should_research = True
        if domain == "IP" and jurisdiction.lower() == "international":
            should_research = True
        if not should_research:
            continue

        if domain == "IP":
            question = "Which current official IP provisions, registries, rules or treaty mechanisms are relevant to the stated product and claim, and what does the source actually establish?"
        elif domain == "TK":
            question = "What authoritative evidence exists for the claimed traditional-knowledge connection or prior-art relevance, and what remains unverified?"
        elif domain == "ABS":
            question = "Do authoritative sources indicate potential biological-resource or access-and-benefit-sharing relevance, and what facts are required before any applicability conclusion?"
        else:
            question = "Which current authoritative regulatory sources apply to the stated product type, purpose and jurisdiction?"

        tasks.append({"agent": f"{domain} Research Agent", "domain": domain, "question": question})

    tasks.append({
        "agent": "Web Research Agent",
        "domain": "REGULATORY",
        "question": "Is there current official guidance, amendment, notification or registry information that could materially change the assessment?",
    })

    return {
        "facts": {
            "jurisdiction": jurisdiction,
            "domains": domains,
            "supported_domains": sorted(supported),
            "unsupported_domains": sorted(unsupported),
        },
        "tasks": tasks,
        "reasoning_labels": ["FACT", "INFERENCE", "RECOMMENDATION", "UNCERTAINTY"],
        "rule": "A research result may support a fact only when the source text supports it; inference and recommendation must remain explicitly labeled.",
    }


def annotate_evidence(
    item: Dict[str, Any],
    *,
    fact: str = "",
    inference: str = "",
    recommendation: str = "",
    uncertainty: str = "",
) -> Dict[str, Any]:
    return {
        **item,
        "fact": fact,
        "inference": inference,
        "recommendation": recommendation,
        "uncertainty": uncertainty,
    }

def web_search(query: str, domains: List[str] | None = None, max_results: int = 5) -> Dict[str, Any]:
    return search_web(query, domains=domains, max_results=max_results)


def official_source_search(query: str, max_results: int = 5) -> Dict[str, Any]:
    return search_web(
        f"{query} official legislation government registry treaty",
        domains=DEFAULT_OFFICIAL_DOMAINS,
        max_results=max_results,
    )


def source_validation(results: Iterable[Dict[str, Any]], query: str = "", domain: str = "") -> List[Dict[str, Any]]:
    return validate_sources(results, query=query, domain=domain)


def evidence_deduplication(items: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen: set[str] = set()
    output: List[Dict[str, Any]] = []
    for item in items:
        url = str(item.get("url", "")).strip().lower()
        title = re.sub(r"\s+", " ", str(item.get("title", "")).strip().lower())
        key = url or title
        if not key or key in seen:
            continue
        seen.add(key)
        output.append(item)
    return output


def _claim_polarity(text: str, terms: Iterable[str]) -> int:
    """Return +1/-1/0 for simple explicit polarity; intentionally conservative."""
    value = str(text or "").lower()
    for term in terms:
        escaped = re.escape(term)
        if re.search(rf"\b(?:not|no|does not|is not|are not|cannot)\s+(?:[a-z ]+\s+)?{escaped}\b", value):
            return -1
        if re.search(rf"\b(?:is|are|must|may|requires|required|allowed|eligible|prohibited|applies)\b(?:[a-z ]+\s+)?{escaped}\b", value):
            return 1
    return 0


def contradiction_detection(
    local_evidence: Iterable[Dict[str, Any]],
    web_evidence: Iterable[Dict[str, Any]] | None = None,
) -> List[Dict[str, Any]]:
    """Flag only explicit polarity conflicts; do not silently resolve them."""
    local = list(local_evidence)
    web = list(web_evidence or [])
    if not local or not web:
        return []

    terms = (
        "required", "prohibited", "allowed", "eligible", "exempt",
        "patentable", "applies", "compliance", "benefit sharing",
    )
    contradictions: List[Dict[str, Any]] = []
    for w in web:
        web_text = str(w.get("evidence_text") or w.get("content") or "")
        wp = _claim_polarity(web_text, terms)
        if not wp:
            continue
        for l in local:
            local_text = str(l.get("text") or l.get("evidence_text") or "")
            lp = _claim_polarity(local_text, terms)
            if lp and lp != wp:
                contradictions.append({
                    "contradiction": True,
                    "sources": [l.get("source"), w.get("url") or w.get("source")],
                    "issue": "Local and external evidence contain opposing explicit statements; the system will not silently select one.",
                    "resolution_status": "REQUIRES_REVIEW",
                })
                break
    return contradictions

@dataclass
class AgenticResearchResult:
    status: str
    research_triggered: bool
    research_tasks: List[Dict[str, Any]]
    web_evidence: List[Dict[str, Any]]
    validated_sources: List[Dict[str, Any]]
    contradictions: List[Dict[str, Any]]
    confidence: Dict[str, Any]
    abstained: bool
    reason: str = ""
    missing_information: List[str] | None = None
    recommended_human_review: str = ""
    agents_used: List[str] | None = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _needs_research(
    existing: List[Dict[str, Any]],
    validation: Dict[str, Any],
    product: Dict[str, Any],
) -> tuple[bool, str]:
    if not existing:
        return True, "No local evidence was retrieved."

    status = str(validation.get("status", "")).upper()
    if status in {"UNSUPPORTED", "PARTIAL", "WEAK", "INSUFFICIENT", "NOT_RUN", "FAILED", "ERROR"}:
        return True, f"Existing validation status is {status or 'UNKNOWN'}."

    if validation.get("unsupported_domains"):
        return True, "One or more routed domains lack direct evidence."

    purpose = str(product.get("purpose", "")).lower()
    current_words = ("current", "latest", "recent", "amendment", "notification", "updated")
    if any(word in purpose for word in current_words):
        return True, "The request depends on current or recently changed information."

    # Existing local evidence can carry source metadata; if it is sparse/unknown,
    # the external agent gets a chance to find a higher-authority source.
    if len(existing) < 2:
        return True, "Local evidence is sparse; additional authoritative research is useful."

    return False, "Existing evidence is sufficient for the agentic research gate."


def _to_structured_web_evidence(item: Dict[str, Any]) -> Dict[str, Any]:
    """Map validated web evidence into a shape the existing IP-SAKTI reasoning layer can consume."""
    return {
        "id": f"web:{item.get('url') or item.get('title') or 'unknown'}",
        "domain": item.get("domain", "UNKNOWN"),
        "source": item.get("source", "Unknown web source"),
        "page": None,
        "chunk": None,
        "retrieval_type": "AGENTIC_WEB",
        "similarity": None,
        "score": float(item.get("confidence", 0.0) or 0.0) * 10.0,
        "evidence_quality": float(item.get("confidence", 0.0) or 0.0),
        "evidence_basis": ["validated_external_source"],
        "matched_terms": [],
        "ingredient_matches": [],
        "domain_matches": {str(item.get("domain", "UNKNOWN")).upper(): []},
        "supported_domains": [str(item.get("domain", "UNKNOWN")).upper()],
        "text": str(item.get("evidence_text", ""))[:1800],
        "url": item.get("url"),
        "authority_level": item.get("authority_level"),
        "authority_tier": item.get("authority_tier"),
        "publication_date": item.get("publication_date"),
        "last_updated": item.get("last_updated"),
        "citation": item.get("citation"),
        "agent": item.get("agent"),
    }


def _confidence(validated: List[Dict[str, Any]], contradictions: List[Dict[str, Any]], failures: List[str]) -> Dict[str, Any]:
    if not validated:
        return {"level": "LOW", "score": 0.20, "tier1_sources": 0, "reason": "No validated external source was available."}
    tier1 = sum(1 for item in validated if int(item.get("authority_tier", 4)) == 1)
    avg = sum(float(item.get("confidence", 0.0)) for item in validated) / len(validated)
    score = min(1.0, avg + min(tier1, 3) * 0.08 - min(len(contradictions), 3) * 0.12 - min(len(failures), 3) * 0.03)
    level = "HIGH" if score >= 0.75 else "MEDIUM" if score >= 0.50 else "LOW"
    return {
        "level": level,
        "score": round(max(0.0, score), 3),
        "tier1_sources": tier1,
        "validated_source_count": len(validated),
        "contradiction_count": len(contradictions),
        "failed_agents": failures,
    }


def run_agentic_research(
    product: Dict[str, Any] | Any,
    existing_evidence: List[Dict[str, Any]] | None = None,
    validation: Dict[str, Any] | None = None,
) -> AgenticResearchResult:
    """Run the optional research stage. It is fail-safe and never raises to /api/analyze."""
    if hasattr(product, "model_dump"):
        product = product.model_dump()
    product = dict(product or {})
    existing_evidence = list(existing_evidence or [])
    validation = dict(validation or {})

    needed, reason = _needs_research(existing_evidence, validation, product)
    if not needed:
        return AgenticResearchResult(
            status="SKIPPED",
            research_triggered=False,
            research_tasks=[],
            web_evidence=[],
            validated_sources=[],
            contradictions=[],
            confidence={"level": "HIGH", "score": 0.85, "reason": reason},
            abstained=False,
            reason=reason,
            missing_information=[],
            recommended_human_review="",
            agents_used=[],
        )

    plan = build_research_plan(product, existing_evidence, validation)
    targeted = build_targeted_queries(product, validation.get("domains") or ["IP"])
    tasks: List[Dict[str, Any]] = []
    for task in plan.get("tasks", []):
        match = next((x for x in targeted if str(x.get("domain", "")).upper() == str(task.get("domain", "")).upper()), None)
        if match:
            tasks.append({**task, "query": match["query"]})
        else:
            tasks.append(task)

    raw_results: List[Dict[str, Any]] = []
    failures: List[str] = []
    max_workers = min(4, max(1, len(tasks)))

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {}
        for task in tasks:
            query = str(task.get("query") or task.get("question") or "").strip()
            futures[executor.submit(web_search, query, domains=None, max_results=5)] = task
        for future in as_completed(futures):
            task = futures[future]
            try:
                result = future.result()
                if result.get("status") == "ERROR":
                    failures.append(str(task.get("agent")))
                for item in result.get("results", []) or []:
                    raw_results.append({
                        **item,
                        "agent": task.get("agent"),
                        "domain": task.get("domain"),
                        "research_question": task.get("question"),
                    })
            except Exception:
                failures.append(str(task.get("agent")))

    raw_results = evidence_deduplication(raw_results)
    validated_all = source_validation(raw_results, query=str(product.get("purpose", "")), domain="")
    validated = [item for item in validated_all if item.get("validated")]
    contradictions = contradiction_detection(existing_evidence, validated)
    confidence = _confidence(validated, contradictions, failures)
    abstained = not validated

    return AgenticResearchResult(
        status="ABSTAIN" if abstained else ("REQUIRES_REVIEW" if contradictions else "SUCCESS"),
        research_triggered=True,
        research_tasks=tasks,
        web_evidence=[_to_structured_web_evidence(x) for x in validated],
        validated_sources=validated,
        contradictions=contradictions,
        confidence=confidence,
        abstained=abstained,
        reason=(
            "I could not verify this claim from sufficient authoritative evidence."
            if abstained
            else reason
        ),
        missing_information=(
            [
                "A verified Tier 1 source supporting the relevant claim.",
                "Any current amendment, notification or jurisdiction-specific fact needed for the decision.",
            ]
            if abstained
            else []
        ),
        recommended_human_review=(
            "Human review is recommended before a consequential IP/TK/ABS decision."
            if abstained or contradictions
            else ""
        ),
        agents_used=sorted({str(task.get("agent")) for task in tasks if task.get("agent")}),
    )



# -------------------------------------------------------------------------
# Adapter from validated agentic evidence to the EXISTING IP-SAKTI evidence
# schema. This reuses the existing domain/ingredient matching and quality
# functions rather than introducing a second local validator.
# -------------------------------------------------------------------------

def _agentic_web_to_existing_evidence(web_evidence, domains, ingredients):
    converted = []
    for item in web_evidence or []:
        text = str(item.get("evidence_text", item.get("text", "")) or "")[:MAX_EVIDENCE_TEXT]
        if not text:
            continue
        domain_matches = find_domain_matches(text, domains)
        ingredient_matches = find_ingredient_matches(text, ingredients)
        supported_domains = [d for d in domains if domain_matches.get(d, [])]
        evidence_item = {
            "id": str(item.get("id", "web:" + str(item.get("url", "")))),
            "domain": str(item.get("domain", "UNKNOWN")).upper(),
            "source": item.get("source", item.get("title", "Unknown web source")),
            "page": None, "chunk": None,
            "retrieval_type": "AGENTIC_WEB",
            "similarity": None,
            "score": float(item.get("confidence", 0.0) or 0.0) * 10.0,
            "evidence_quality": 0.0,
            "evidence_basis": ["validated_external_source"],
            "matched_terms": [],
            "ingredient_matches": ingredient_matches,
            "domain_matches": domain_matches,
            "domain_match": bool(str(item.get("domain", "")).upper() in domains),
            "supported_domains": supported_domains,
            "text": text,
            "url": item.get("url"),
            "authority_level": item.get("authority_level"),
            "authority_tier": item.get("authority_tier"),
            "publication_date": item.get("publication_date"),
            "last_updated": item.get("last_updated"),
            "citation": item.get("citation"),
            "agent": item.get("agent"),
        }
        evidence_item["evidence_quality"] = calculate_evidence_quality(evidence_item)
        converted.append(evidence_item)
        if len(converted) >= AGENTIC_MAX_WEB_EVIDENCE:
            break
    return converted


def _run_agentic_stage(product, evidence, validation):
    disabled = {
        "status": "DISABLED", "research_triggered": False, "research_tasks": [],
        "web_evidence": [], "validated_sources": [], "contradictions": [],
        "confidence": {"level": "LOW", "score": 0.0, "reason": "Agentic AI is disabled."},
        "abstained": False,
        "reason": "Existing IP-SAKTI analysis continues without web research.",
        "missing_information": [], "recommended_human_review": "", "agents_used": [],
    }
    if not AGENTIC_AI_ENABLED:
        return disabled
    try:
        result = run_agentic_research(product=product, existing_evidence=evidence, validation=validation)
        return result.to_dict() if hasattr(result, "to_dict") else (result if isinstance(result, dict) else disabled)
    except Exception as exc:
        logger.exception("Agentic research failed; preserving existing analysis: %r", exc)
        failed = dict(disabled)
        failed.update({
            "status": "FAILED",
            "reason": "Agentic research failed. Existing local evidence analysis was preserved.",
            "error": type(exc).__name__,
        })
        return failed



# =========================================================
# AGENTIC AI CHAT — REQUEST SCHEMA
# =========================================================

class AgentChatRequest(BaseModel):

    query: str = Field(..., min_length=1, max_length=2000)

    jurisdiction: str = Field(default="India", max_length=200)

    language: str = Field(default="en", max_length=10)

    @field_validator("query", "jurisdiction")
    @classmethod
    def clean_text(cls, value):
        value = str(value).strip()
        if not value:
            raise ValueError("Field cannot be empty.")
        return value


# =========================================================
# AGENTIC AI CHAT — ORCHESTRATOR
# =========================================================
# This function does NOT introduce a second retrieval system, a second
# Knowledge Graph, or a second LLM-reasoning pipeline. It orchestrates
# the EXISTING IP-SAKTI components — search_corpus() (hybrid/BM25/
# vector/KG retrieval), validate_evidence(), _run_agentic_stage()
# (the existing fail-safe web-research layer), generate_llm_reasoning()
# (the existing grounded LLM call), calculate_confidence(),
# build_source_records(), identify_missing_information() and
# build_human_escalation() — in the same way /api/analyze already does.

def _build_chat_pseudo_product(query: str, jurisdiction: str) -> ProductInput:
    """
    The existing classification/retrieval/reasoning functions are
    written against ProductInput (product_name, ingredients, purpose,
    product_type, jurisdiction, based_on_traditional_knowledge). Free-
    text chat questions don't have that structure, so the question is
    carried in `purpose` (the field every existing routing/evidence
    function actually reads text from), which lets the chat feature
    reuse detect_domains(), search_corpus(), generate_llm_reasoning()
    etc. unchanged instead of forking a parallel implementation.
    """
    return ProductInput(
        product_name="Agentic AI chat question",
        ingredients=[],
        purpose=query,
        product_type="General IP / TK / ABS inquiry",
        jurisdiction=jurisdiction or "India",
        based_on_traditional_knowledge="unknown",
    )


def run_agent_chat(query: str, jurisdiction: str = "India", language: str = "en") -> Dict[str, Any]:

    agent_trace: List[str] = ["Query intent identified"]
    tools_used: List[str] = []

    jurisdiction = str(jurisdiction or "India").strip() or "India"
    language = normalize_language_code(language)

    pseudo_product = _build_chat_pseudo_product(query, jurisdiction)

    # ---------------------------------------------------
    # 1. DOMAIN ROUTING (existing function)
    # ---------------------------------------------------
    domains = detect_domains(pseudo_product)
    agent_trace.append(f"Domains identified: {', '.join(domains)}")

    # ---------------------------------------------------
    # 2. EXISTING IP / TK / ABS / KNOWLEDGE-GRAPH RETRIEVAL
    #    (search_corpus already covers hybrid/BM25/vector/KG)
    # ---------------------------------------------------
    local_evidence = search_corpus(query, domains)
    tools_used.append("ip_sakti_knowledge_retrieval")
    agent_trace.append(
        f"IP-SAKTI knowledge base searched ({len(local_evidence)} evidence item(s))"
    )

    validation = validate_evidence(local_evidence, domains)

    if "TK" in domains:
        tools_used.append("tk_retrieval")
        agent_trace.append("TK knowledge checked")
    if "ABS" in domains:
        tools_used.append("abs_retrieval")
        agent_trace.append("ABS knowledge checked")
    if local_evidence:
        tools_used.append("knowledge_graph")
        agent_trace.append("Knowledge Graph consulted")

    # ---------------------------------------------------
    # 3. WEB SEARCH — reuses the EXISTING fail-safe agentic
    #    research layer (_run_agentic_stage/run_agentic_research),
    #    which already decides whether web research is needed and
    #    never breaks the response if web search fails.
    # ---------------------------------------------------
    agentic_result = _run_agentic_stage(pseudo_product, local_evidence, validation)

    web_evidence = agentic_result.get("web_evidence", []) or []
    if agentic_result.get("research_triggered"):
        tools_used.append("web_search")
        if web_evidence:
            agent_trace.append(
                f"Web search performed ({len(web_evidence)} validated source(s))"
            )
        else:
            agent_trace.append("Web search performed (no validated sources found)")
    else:
        agent_trace.append("Web search skipped (existing evidence sufficient)")

    combined_evidence = list(local_evidence) + list(web_evidence)

    # Re-validate against the combined local + web evidence so domain
    # support reflects everything the agent actually found.
    if web_evidence:
        validation = validate_evidence(combined_evidence, domains)

    agent_trace.append("Evidence validated")

    # ---------------------------------------------------
    # 4. GROUNDED LLM REASONING (existing function — same
    #    no-invented-facts / no-invented-law rules as /api/analyze)
    # ---------------------------------------------------
    llm_result = generate_llm_reasoning(pseudo_product, domains, combined_evidence, validation)

    confidence = calculate_confidence(combined_evidence, validation)
    sources = build_source_records(combined_evidence)
    missing_information = identify_missing_information(
        pseudo_product, domains, validation, combined_evidence
    )
    escalation = build_human_escalation(domains, validation, confidence, missing_information)

    agent_trace.append("Answer generated")

    # ---------------------------------------------------
    # 5. ASSEMBLE THE ANSWER — abstain rather than guess
    # ---------------------------------------------------
    if llm_result.get("status") == "SUCCESS":
        analysis = llm_result.get("analysis", {}) or {}
        parts = []
        if analysis.get("summary"):
            parts.append(str(analysis["summary"]))
        if analysis.get("evidence_interpretation"):
            parts.append(str(analysis["evidence_interpretation"]))
        answer = "\n\n".join(parts).strip() or (
            "Insufficient evidence. I could not find grounded evidence "
            "to answer this question for the selected jurisdiction."
        )
    elif not combined_evidence:
        answer = (
            "Insufficient evidence. No relevant material was found in the "
            "IP-SAKTI knowledge base or via web search for this question "
            f"in the {jurisdiction} jurisdiction. Please verify with an "
            "appropriate qualified professional or facilitator."
        )
    else:
        answer = (
            "Insufficient evidence. Evidence was retrieved but the "
            "reasoning engine could not be reached, so no grounded "
            "conclusion can be generated right now. Retrieved sources "
            "are shown below for manual review."
        )

    return {
        "answer": answer,
        "sources": sources,
        "citations": sources,
        "confidence": confidence,
        "domains": domains,
        "tools_used": sorted(set(tools_used)),
        "agent_trace": agent_trace,
        "needs_human_review": bool(escalation.get("recommended", False)),
        "human_review": escalation,
        "missing_information": missing_information,
        "recommended_verification": (llm_result.get("analysis", {}) or {}).get(
            "recommended_verification", []
        ),
        "disclaimer": (
            "IP-SAKTI provides evidence-grounded information and does not "
            "provide legal advice."
        ),
    }


# =========================================================
# AGENTIC AI CHAT — POST /api/agent/chat
# =========================================================
@app.post("/api/agent/chat")
def agent_chat(request: AgentChatRequest):
    try:
        result = run_agent_chat(
            query=request.query,
            jurisdiction=request.jurisdiction,
            language=request.language,
        )

        # Translate only the user-facing answer. Source titles, URLs,
        # citations, and evidence text remain unchanged.
        if request.language in {"hi", "mr"} and result.get("answer"):
            result["answer"] = translate_text(
                result["answer"],
                "en",
                request.language,
            )

        result["jurisdiction"] = request.jurisdiction
        result["language"] = request.language
        return result

    except Exception as exc:
        logger.exception("Agent chat failed safely: %r", exc)
        return {
            "answer": (
                "Insufficient evidence. The Agentic AI layer could not "
                "complete the requested research safely."
            ),
            "sources": [],
            "citations": [],
            "confidence": {
                "level": "LOW",
                "score": 0.0,
                "basis": "Agent execution failed safely.",
            },
            "jurisdiction": request.jurisdiction,
            "language": request.language,
            "tools_used": [],
            "agent_trace": [
                "Agent request received",
                "Agent execution failed safely",
                "No unsupported conclusion returned",
            ],
            "needs_human_review": True,
            "missing_information": [
                "Reliable evidence could not be retrieved."
            ],
            "recommended_verification": [
                "Verify the question using an authoritative "
                "jurisdiction-specific source."
            ],
            "disclaimer": (
                "IP-SAKTI provides evidence-grounded information "
                "and does not provide legal advice."
            ),
        }

class AgenticResearchRequest(ProductInput):
    existing_evidence: List[Dict[str, Any]] = Field(default_factory=list, max_length=50)
    validation: Dict[str, Any] = Field(default_factory=dict)


@app.post("/api/agentic-research")
def agentic_research_endpoint(request: AgenticResearchRequest):
    result = _run_agentic_stage(
        request.model_dump(exclude={"existing_evidence", "validation"}),
        request.existing_evidence,
        request.validation,
    )
    return {
        "status": result.get("status", "FAILED"),
        "research_triggered": result.get("research_triggered", False),
        "research_tasks": result.get("research_tasks", []),
        "web_evidence": result.get("web_evidence", []),
        "validated_sources": result.get("validated_sources", []),
        "contradictions": result.get("contradictions", []),
        "confidence": result.get("confidence", {}),
        "abstained": result.get("abstained", False),
    }


# =========================================================
# MAIN ANALYZE ENDPOINT
# =========================================================

@app.post(
    "/api/analyze"
)
def analyze_product(
    product: ProductInput
):

    logger.info(
        "=" * 70
    )

    logger.info(
        "IP-SAKTI ANALYSIS"
    )

    logger.info(
        "=" * 70
    )

    # -----------------------------------------------------
    # CLASSIFICATION
    # -----------------------------------------------------

    classification = classify_product(
        product
    )

    # Enhanced MVP classification is additive. The original
    # classification object is preserved for backward
    # compatibility with existing clients.
    product_classification = classify_product_v2(
        product
    )

    # -----------------------------------------------------
    # DOMAIN DETECTION
    # -----------------------------------------------------

    domains = detect_domains(
        product
    )

    # -----------------------------------------------------
    # SEARCH QUERY
    # -----------------------------------------------------

    query = build_search_query(
        product,
        domains
    )

    # -----------------------------------------------------
    # EVIDENCE RETRIEVAL
    # -----------------------------------------------------

    evidence = search_corpus(

        query=query,

        domains=domains,

        ingredients=product.ingredients,

        top_k=TOP_K
    )

    logger.info(
        "Product: %s",
        product.product_name
    )

    logger.info(
        "Ingredients: %s",
        product.ingredients
    )

    logger.info(
        "Domains: %s",
        domains
    )

    logger.info(
        "Evidence found: %d",
        len(evidence)
    )

    logger.info(
        "BGE available: %s",
        EMBEDDINGS_AVAILABLE
    )

    logger.info(
        "Embedding model: %s",
        EMBEDDING_MODEL
    )

    # -----------------------------------------------------
    # VALIDATION
    # -----------------------------------------------------

    validation = validate_evidence(
        evidence,
        domains
    )

    logger.info(
        "Validation status: %s",
        validation.get(
            "status"
        )
    )

    logger.info(
        "Supported domains: %s",
        validation.get(
            "supported_domains"
        )
    )

    logger.info(
        "Unsupported domains: %s",
        validation.get(
            "unsupported_domains"
        )
    )

    # -----------------------------------------------------
    # OPTIONAL AGENTIC RESEARCH
    # -----------------------------------------------------

    agentic_research = _run_agentic_stage(
        product,
        evidence,
        validation
    )

    agentic_evidence = _agentic_web_to_existing_evidence(
        agentic_research.get("web_evidence", []),
        domains,
        product.ingredients
    )

    # Additive evidence fusion: original local evidence is untouched.
    evidence_for_reasoning = list(evidence) + agentic_evidence

    validation_for_reasoning = validate_evidence(
        evidence_for_reasoning,
        domains
    )

    # -----------------------------------------------------
    # LLM REASONING
    # -----------------------------------------------------

    llm_reasoning = (
        generate_llm_reasoning(
            product,
            domains,
            evidence_for_reasoning,
            validation_for_reasoning
        )
    )

    # -----------------------------------------------------
    # CONFIDENCE
    # -----------------------------------------------------

    confidence = calculate_confidence(
        evidence,
        validation
    )

    # -----------------------------------------------------
    # SOURCES
    # -----------------------------------------------------

    sources = []

    for item in evidence:

        source = item.get(
            "source",
            "Unknown source"
        )

        if source not in sources:

            sources.append(
                source
            )

    # -----------------------------------------------------
    # REASONING METADATA
    # -----------------------------------------------------

    if evidence:

        retrieval_methods = sorted(
            set(
                item.get(
                    "retrieval_type",
                    "UNKNOWN"
                )
                for item in evidence
            )
        )

        reasoning = {

            "summary":
                (
                    "The product was routed to the "
                    "detected domains and evidence was "
                    "retrieved using domain filtering, "
                    "ingredient matching, keyword scoring "
                    "and BGE semantic retrieval when available."
                ),

            "domains_considered":
                domains,

            "supported_domains":
                validation.get(
                    "supported_domains",
                    []
                ),

            "unsupported_domains":
                validation.get(
                    "unsupported_domains",
                    []
                ),

            "search_query":
                query,

            "evidence_count":
                len(evidence),

            "sources":
                sources,

            "retrieval_methods":
                retrieval_methods,

            "embedding_model":
                EMBEDDING_MODEL,

            "note":
                (
                    "Domain metadata is not treated as "
                    "evidence. Direct textual domain matches "
                    "are required for domain support. "
                    "This prototype does not establish "
                    "legal compliance, legal violation, "
                    "legal liability, patentability, "
                    "ownership, or infringement."
                )
        }

    else:

        reasoning = {

            "summary":
                (
                    "The system could not establish "
                    "sufficient domain-aligned evidence "
                    "from the current corpus."
                ),

            "domains_considered":
                domains,

            "supported_domains":
                [],

            "unsupported_domains":
                domains,

            "search_query":
                query,

            "evidence_count":
                0,

            "retrieval_methods": [

                "Domain filtering",

                "Ingredient matching",

                "Keyword retrieval",

                "BGE semantic retrieval"
            ],

            "limitation":
                (
                    "The system abstains instead of "
                    "returning unrelated documents."
                )
        }

    # -----------------------------------------------------
    # ACTION PLAN
    # -----------------------------------------------------

    action_plan = build_action_plan(

        domains=domains,

        evidence=evidence,

        validation=validation
    )

    # -----------------------------------------------------
    # MVP ENHANCEMENT OUTPUTS
    # -----------------------------------------------------

    missing_information = identify_missing_information(
        product=product,
        domains=domains,
        validation=validation,
        evidence=evidence
    )

    domain_routing = build_domain_routing_summary(
        product=product,
        domains=domains,
        validation=validation
    )

    source_records = build_source_records(
        evidence
    )

    safe_decision = build_safe_decision(
        domains=domains,
        evidence=evidence,
        validation=validation,
        confidence=confidence,
        missing_information=missing_information
    )

    human_escalation = build_human_escalation(
        domains=domains,
        validation=validation,
        confidence=confidence,
        missing_information=missing_information
    )

    # Narrative fields exposed directly for the updated
    # Streamlit MVP. The original llm_reasoning object remains
    # untouched.
    ai_assessment = (
        llm_reasoning.get(
            "analysis",
            {}
        )
        if isinstance(
            llm_reasoning,
            dict
        )
        else {}
    )

    recommended_verification = []

    if isinstance(
        ai_assessment,
        dict
    ):

        recommended_verification = (
            ai_assessment.get(
                "recommended_verification",
                []
            )
            or []
        )

    if not recommended_verification:

        recommended_verification = list(
            missing_information
        )

    # -----------------------------------------------------
    # FINAL RESPONSE
    # -----------------------------------------------------

    return {

        "app_version":
            APP_VERSION,

        "product":
            product.model_dump(),

        "classification":
            classification,

        "domains":
            domains,

        "search_query":
            query,

        "evidence":
            sanitize_evidence(
                evidence
            ),

        "reasoning":
            reasoning,

        "llm_reasoning":
            llm_reasoning,

        "validation":
            validation,

        "confidence":
            confidence,

        "action_plan":
            action_plan,

        # =================================================
        # UPDATED STREAMLIT MVP CONTRACT
        # =================================================

        "product_classification":
            product_classification,

        "domain_routing":
            domain_routing,

        "evidence_validation":
            validation,

        "evidence_confidence":
            confidence,

        # Keep "evidence" as the canonical retrieved-evidence
        # field for backward compatibility.
        "retrieved_evidence":
            sanitize_evidence(
                evidence
            ),

        "sources":
            source_records,

        "ai_assessment":
            ai_assessment,

        "recommended_verification":
            recommended_verification,

        "missing_information":
            missing_information,

        "recommended_action_plan":
            action_plan,

        "human_escalation":
            human_escalation,

        "safe_decision":
            safe_decision,

        "agentic_research":
            agentic_research,

        "evidence_fusion": {
            "local_evidence_count": len(evidence),
            "agentic_validated_evidence_count": len(agentic_evidence),
            "llm_reasoning_evidence_count": len(evidence_for_reasoning),
            "note": "Validated agentic web evidence is additive to local IP-SAKTI evidence."
        },

        "mvp":
            {
                "name":
                    "IP-SAKTI Evidence-First MVP",

                "version":
                    APP_VERSION,

                "language_service":
                    (
                        "Bhashini"
                        if BHASHINI_ENABLED
                        else "fallback"
                    ),

                "features": [
                    "Product classification",
                    "IP/TK/ABS domain routing",
                    "Hybrid evidence retrieval",
                    "Evidence validation",
                    "Evidence confidence",
                    "Grounded Ollama reasoning",
                    "Missing-information detection",
                    "Human escalation",
                    "Safe abstention",
                    "Multilingual UI translation",
                    "Optional agentic web research",
                    "Source authority validation",
                    "Contradiction detection"
                ],

                "legal_disclaimer":
                    (
                        "Prototype only. The system does not "
                        "provide legal advice or establish legal "
                        "compliance, liability, patentability, "
                        "ownership, infringement, TK rights or "
                        "ABS obligations."
                    )
            }
    }


# =========================================================
# ROOT
# =========================================================

@app.get("/")
def root():

    corpus = load_corpus()

    return {

        "message":
            "IP-SAKTI MVP API is running",

        "version":
            APP_VERSION,

        "docs":
            "/docs",

        "conversation":
            (
                "/api/conversation/start"
                if conversation_router
                is not None
                else None
            ),

        "corpus_chunks":
            len(corpus),

        "llm":
            OLLAMA_MODEL,

        "bge_embeddings":
            EMBEDDINGS_AVAILABLE,

        "embedding_model":
            EMBEDDING_MODEL,

        "language_service":
            (
                "Bhashini"
                if BHASHINI_ENABLED
                else "fallback"
            ),

        "supported_languages":
            SUPPORTED_LANGUAGES
    }


# =========================================================
# HEALTH CHECK
# =========================================================

@app.get(
    "/api/health"
)
def health():

    corpus = load_corpus()

    return {

        "status":
            "ok",

        "version":
            APP_VERSION,

        "corpus_available":
            bool(corpus),

        "corpus_chunks":
            len(corpus),

        "ollama_model":
            OLLAMA_MODEL,

        "bge_embeddings":
            EMBEDDINGS_AVAILABLE,

        "embedding_model":
            EMBEDDING_MODEL,

        "conversation_router":
            conversation_router
            is not None,

        "bhashini_enabled":
            BHASHINI_ENABLED,

        "supported_languages":
            SUPPORTED_LANGUAGES
    }


# =========================================================
# DEVELOPMENT CORPUS RELOAD
# =========================================================

@app.post(
    "/api/admin/reload-corpus"
)
def reload_corpus():

    """
    Development helper.

    For production, protect this endpoint
    with authentication or remove it.
    """

    corpus = load_corpus(
        force_reload=True
    )

    return {

        "status":
            "reloaded",

        "corpus_chunks":
            len(corpus)
    }


# =========================================================
# LOCAL START
# =========================================================

if __name__ == "__main__":

    import uvicorn

    uvicorn.run(

        "main:app",

        host="127.0.0.1",

        port=8000,

        reload=True
    )