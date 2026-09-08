"""
language_config.py

Single source of truth for:
  - which languages IP-SAKTI supports in v1
  - the language codes Bhashini/ULCA pipelines expect
  - whether the real Bhashini API is enabled or we fall back

Nothing here talks to a network. Pure config + lookups.
"""

import os


# =========================================================
# SUPPORTED LANGUAGES (v1)
# =========================================================

# Internal canonical code -> display label (used in Streamlit).
SUPPORTED_LANGUAGES = {
    "en": "English",
    "hi": "हिंदी",
    "mr": "मराठी",
}

# The language all retrieval/classification/reasoning happens in.
# This NEVER changes per-request -- it is the pivot language.
CANONICAL_LANGUAGE = "en"

# Bhashini/ULCA pipeline language codes. For Bhashini these
# happen to already be ISO 639-1 codes identical to our internal
# ones, but this indirection exists so a future language (e.g.
# a code Bhashini spells differently) doesn't require touching
# every call site -- only this map.
BHASHINI_LANGUAGE_CODES = {
    "en": "en",
    "hi": "hi",
    "mr": "mr",
}


def is_supported_language(code: str) -> bool:
    return code in SUPPORTED_LANGUAGES


def to_bhashini_code(code: str) -> str:
    """
    Maps our internal language code to whatever code Bhashini's
    pipeline API expects. ASSUMPTION: Bhashini's NMT pipeline
    config accepts plain ISO codes ("en", "hi", "mr") in
    sourceLanguage/targetLanguage fields -- verify against your
    pipeline's /pipeline-config response once real credentials
    are available; this map is the only place to change if not.
    """
    return BHASHINI_LANGUAGE_CODES.get(code, code)


# =========================================================
# BHASHINI ENABLE / FALLBACK
# =========================================================

def bhashini_enabled() -> bool:
    return os.getenv(
        "BHASHINI_ENABLED",
        "false"
    ).strip().lower() in ("1", "true", "yes")


BHASHINI_API_KEY = os.getenv("BHASHINI_API_KEY", "")
BHASHINI_USER_ID = os.getenv("BHASHINI_USER_ID", "")
BHASHINI_PIPELINE_ID = os.getenv("BHASHINI_PIPELINE_ID", "")

# ASSUMPTION: standard Bhashini/ULCA inference endpoint. Confirm
# against your Bhashini dashboard/onboarding docs; override via
# env if your pipeline uses a different compute endpoint.
BHASHINI_PIPELINE_COMPUTE_URL = os.getenv(
    "BHASHINI_PIPELINE_COMPUTE_URL",
    "https://dhruva-api.bhashini.gov.in/services/inference/pipeline",
)

BHASHINI_CONFIG_URL = os.getenv(
    "BHASHINI_CONFIG_URL",
    "https://meity-auth.ulcacontrib.org/ulca/apis/v0/model/getModelsPipeline",
)