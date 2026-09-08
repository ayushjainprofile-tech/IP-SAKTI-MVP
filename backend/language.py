"""
routers/language.py

Thin FastAPI surface over BhashiniService, plus ONE integration
endpoint (/api/analyze/multilingual) that wraps the EXISTING
/api/analyze pipeline with translation at the edges only.

No retrieval, classification, or reasoning logic lives here --
it all still runs inside main.analyze_product(). This file only
translates request text in, and translates specific known
response text fields back out.
"""

import logging

from fastapi import APIRouter
from pydantic import BaseModel
from typing import List, Optional

from config.language_config import SUPPORTED_LANGUAGES, CANONICAL_LANGUAGE
from services.bhashini_service import bhashini_service

logger = logging.getLogger("ip-sakti.language")

router = APIRouter(prefix="/api/language", tags=["language"])


# =========================================================
# SIMPLE TRANSLATE ENDPOINTS (used by Streamlit for question
# text + user answers)
# =========================================================

class TranslateRequest(BaseModel):
    text: str
    source_lang: str
    target_lang: str


class TranslateResponse(BaseModel):
    text: str
    source_lang: str
    target_lang: str
    fallback: bool
    engine: str


@router.post("/translate", response_model=TranslateResponse)
def translate(payload: TranslateRequest):

    if payload.target_lang == CANONICAL_LANGUAGE:
        result = bhashini_service.translate_to_english(
            payload.text, payload.source_lang
        )
    else:
        result = bhashini_service.translate_from_english(
            payload.text, payload.target_lang
        )

    return result.to_dict()


class TranslateBatchRequest(BaseModel):
    texts: List[str]
    source_lang: str
    target_lang: str


class TranslateBatchResponse(BaseModel):
    results: List[TranslateResponse]


@router.post("/translate-batch", response_model=TranslateBatchResponse)
def translate_batch(payload: TranslateBatchRequest):

    results = []

    for text in payload.texts:

        if payload.target_lang == CANONICAL_LANGUAGE:
            result = bhashini_service.translate_to_english(
                text, payload.source_lang
            )
        else:
            result = bhashini_service.translate_from_english(
                text, payload.target_lang
            )

        results.append(result.to_dict())

    return {"results": results}


@router.get("/supported")
def supported_languages():
    return {
        "languages": SUPPORTED_LANGUAGES,
        "canonical": CANONICAL_LANGUAGE,
    }


# =========================================================
# MULTILINGUAL ANALYZE WRAPPER
# =========================================================
#
# ASSUMPTION: this imports ProductInput and analyze_product
# directly from your existing backend/main.py. The import is
# deferred (inside the function, not at module import time) to
# avoid a circular import, since main.py is the module that
# registers this router. If your ProductInput/analyze_product
# live somewhere else, this is the ONE section to repoint.
# =========================================================

# Narrative text fields inside the analyze_product() response
# that are safe to translate for display. Evidence text, source
# names, and citations are deliberately excluded -- they must
# stay tied to the original corpus language/wording.
_TRANSLATABLE_TOP_LEVEL = [
    ("reasoning", "summary"),
]

_TRANSLATABLE_LLM_FIELDS = [
    "summary",
    "evidence_interpretation",
    "limitations",
]

_TRANSLATABLE_LLM_LIST_FIELDS = [
    "risks",
    "recommended_verification",
]

_TRANSLATABLE_DOMAIN_ANALYSIS_KEYS = ["IP", "TK", "ABS"]


class MultilingualAnalyzeRequest(BaseModel):
    product_name: str
    ingredients: List[str] = []
    purpose: str
    product_type: str
    jurisdiction: str = "India"
    based_on_traditional_knowledge: str
    language: str = CANONICAL_LANGUAGE


def _translate_analysis_result(analysis: dict, target_lang: str) -> dict:
    """
    Mutates a COPY of the analyze_product() response, translating
    only known narrative fields. If anything about the expected
    shape is missing (e.g. llm_reasoning wasn't SUCCESS), this
    degrades gracefully and leaves those fields untouched rather
    than raising -- an assessment must never crash because
    translation had nothing to translate.
    """

    if target_lang == CANONICAL_LANGUAGE:
        return analysis

    out = dict(analysis)

    # reasoning.summary
    reasoning = dict(out.get("reasoning") or {})
    if reasoning.get("summary"):
        reasoning["summary"] = bhashini_service.translate_from_english(
            reasoning["summary"], target_lang
        ).text
    out["reasoning"] = reasoning

    # llm_reasoning.analysis.*
    llm_reasoning = dict(out.get("llm_reasoning") or {})
    analysis_block = llm_reasoning.get("analysis")

    if isinstance(analysis_block, dict):

        analysis_block = dict(analysis_block)

        for field in _TRANSLATABLE_LLM_FIELDS:
            if analysis_block.get(field):
                analysis_block[field] = bhashini_service.translate_from_english(
                    analysis_block[field], target_lang
                ).text

        for field in _TRANSLATABLE_LLM_LIST_FIELDS:
            values = analysis_block.get(field)
            if isinstance(values, list) and values:
                analysis_block[field] = [
                    bhashini_service.translate_from_english(v, target_lang).text
                    for v in values
                ]

        domain_analysis = analysis_block.get("domain_analysis")
        if isinstance(domain_analysis, dict):
            domain_analysis = dict(domain_analysis)
            for key in _TRANSLATABLE_DOMAIN_ANALYSIS_KEYS:
                if domain_analysis.get(key):
                    domain_analysis[key] = bhashini_service.translate_from_english(
                        domain_analysis[key], target_lang
                    ).text
            analysis_block["domain_analysis"] = domain_analysis

        llm_reasoning["analysis"] = analysis_block

    out["llm_reasoning"] = llm_reasoning

    # Flag on the response so the UI can show
    # "translated from English" + fallback state if any
    # individual field silently fell back.
    out["_language"] = {
        "canonical": CANONICAL_LANGUAGE,
        "displayed_in": target_lang,
    }

    return out


class TranslateAnalysisRequest(BaseModel):
    analysis: dict
    target_lang: str


@router.post("/translate-analysis")
def translate_analysis(payload: TranslateAnalysisRequest):
    """
    Used by Streamlit: call /api/analyze as normal (English),
    then pass the raw response here to get a display copy with
    known narrative fields translated. Evidence/citations are
    left untouched. See _translate_analysis_result() for exactly
    which fields are translated.
    """
    return _translate_analysis_result(payload.analysis, payload.target_lang)


@router.post("/analyze-multilingual")
def analyze_multilingual(payload: MultilingualAnalyzeRequest):

    # Deferred import -- see ASSUMPTION above.
    from main import analyze_product, ProductInput

    target_lang = payload.language

    # 1) Normalize free-text fields to English BEFORE they touch
    #    classification/retrieval. product_type/jurisdiction are
    #    left as-is since they're picked from fixed option sets
    #    in the UI, not free text.
    product_name_en = bhashini_service.translate_to_english(
        payload.product_name, target_lang
    ).text

    purpose_en = bhashini_service.translate_to_english(
        payload.purpose, target_lang
    ).text

    ingredients_en = [
        bhashini_service.translate_to_english(i, target_lang).text
        for i in payload.ingredients
    ]

    product = ProductInput(
        product_name=product_name_en,
        ingredients=ingredients_en,
        purpose=purpose_en,
        product_type=payload.product_type,
        jurisdiction=payload.jurisdiction,
        based_on_traditional_knowledge=payload.based_on_traditional_knowledge,
    )

    # 2) Run the EXISTING, UNMODIFIED evidence-first pipeline.
    result = analyze_product(product)

    # 3) Translate only known narrative fields back for display.
    return _translate_analysis_result(result, target_lang)