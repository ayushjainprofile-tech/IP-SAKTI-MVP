"""
bhashini_service.py

A thin language layer around the real Bhashini/ULCA pipeline API.

WHAT THIS FILE IS RESPONSIBLE FOR:
    - detect_language()
    - translate_to_english()
    - translate_from_english()
    - speech_to_text()   (interface + fallback; not wired into
                           Streamlit in v1 -- see FUTURE SCOPE)
    - text_to_speech()   (interface + fallback; same as above)

WHAT THIS FILE IS NEVER RESPONSIBLE FOR:
    - legal/TK/ABS reasoning
    - retrieval
    - evidence, citations, confidence, abstention

Those all stay in the existing IP-SAKTI engine (main.py). This
service is only ever called BEFORE retrieval (to normalize user
input to English) and AFTER reasoning (to translate the already-
final, already-grounded answer for display).

FALLBACK MODE
=============
If BHASHINI_ENABLED=false, or a real API call fails for any
reason, this service NEVER fabricates a translation. It returns
the original text unchanged, tagged with fallback=True, so the
caller can show a clear "(machine translation unavailable)"
label instead of silently pretending a translation happened.
"""

import logging
import requests

from config.language_config import (
    bhashini_enabled,
    to_bhashini_code,
    is_supported_language,
    CANONICAL_LANGUAGE,
    BHASHINI_API_KEY,
    BHASHINI_USER_ID,
    BHASHINI_PIPELINE_ID,
    BHASHINI_PIPELINE_COMPUTE_URL,
)

logger = logging.getLogger("ip-sakti.bhashini")


class TranslationResult:
    """
    Plain result object so callers never have to guess dict keys.
    """

    def __init__(self, text, source_lang, target_lang, fallback, engine):
        self.text = text
        self.source_lang = source_lang
        self.target_lang = target_lang
        self.fallback = fallback
        self.engine = engine

    def to_dict(self):
        return {
            "text": self.text,
            "source_lang": self.source_lang,
            "target_lang": self.target_lang,
            "fallback": self.fallback,
            "engine": self.engine,
        }


class BhashiniService:

    def __init__(self):
        self.enabled = bhashini_enabled()

        if not self.enabled:
            logger.warning(
                "BhashiniService running in FALLBACK mode "
                "(BHASHINI_ENABLED=false). Translations will "
                "pass text through unchanged and be labelled "
                "as fallback."
            )

    # -----------------------------------------------------
    # LOW-LEVEL PIPELINE CALL
    # -----------------------------------------------------

    def _call_nmt_pipeline(self, text, source_lang, target_lang):
        """
        ASSUMPTION: this follows the standard Bhashini/ULCA
        "pipelineTasks" inference request shape used by their
        NMT (translation) task. Verify field names against your
        own pipeline's config response
        (BHASHINI_CONFIG_URL / getModelsPipeline) before relying
        on this in production -- task/config IDs can differ per
        onboarded pipeline.
        """

        payload = {
            "pipelineTasks": [
                {
                    "taskType": "translation",
                    "config": {
                        "language": {
                            "sourceLanguage": to_bhashini_code(source_lang),
                            "targetLanguage": to_bhashini_code(target_lang),
                        }
                    },
                }
            ],
            "inputData": {
                "input": [{"source": text}]
            },
        }

        headers = {
            "Content-Type": "application/json",
            "userID": BHASHINI_USER_ID,
            "ulcaApiKey": BHASHINI_API_KEY,
        }

        if BHASHINI_PIPELINE_ID:
            headers["pipelineId"] = BHASHINI_PIPELINE_ID

        response = requests.post(
            BHASHINI_PIPELINE_COMPUTE_URL,
            json=payload,
            headers=headers,
            timeout=15,
        )
        response.raise_for_status()

        data = response.json()

        # ASSUMPTION: response shape is
        # data["pipelineResponse"][0]["output"][0]["target"]
        # per standard Bhashini NMT task output. Adjust this one
        # line if your pipeline's real response differs.
        return (
            data["pipelineResponse"][0]["output"][0]["target"]
        )

    # -----------------------------------------------------
    # PUBLIC API
    # -----------------------------------------------------

    def detect_language(self, text: str) -> str:
        """
        v1: Bhashini's language-detection (LID) task is not
        wired in yet -- the Streamlit language selector is the
        source of truth for which language the user is typing
        in, so this is only a safety net. Falls back to
        CANONICAL_LANGUAGE ("en") if called without a hint.

        FUTURE SCOPE: swap this body for a real LID pipeline
        call using the same _call_nmt_pipeline() pattern with
        taskType="language-detection".
        """
        return CANONICAL_LANGUAGE

    def translate_to_english(self, text: str, source_lang: str) -> TranslationResult:
        return self._translate(text, source_lang, CANONICAL_LANGUAGE)

    def translate_from_english(self, text: str, target_lang: str) -> TranslationResult:
        return self._translate(text, CANONICAL_LANGUAGE, target_lang)

    def _translate(self, text: str, source_lang: str, target_lang: str) -> TranslationResult:

        text = (text or "").strip()

        if not text:
            return TranslationResult(text, source_lang, target_lang, fallback=False, engine="noop")

        if source_lang == target_lang:
            return TranslationResult(text, source_lang, target_lang, fallback=False, engine="identity")

        if not is_supported_language(source_lang) or not is_supported_language(target_lang):
            logger.warning(
                "Unsupported language pair (%s -> %s); returning "
                "original text unchanged.",
                source_lang, target_lang,
            )
            return TranslationResult(text, source_lang, target_lang, fallback=True, engine="unsupported_language")

        if not self.enabled:
            return TranslationResult(text, source_lang, target_lang, fallback=True, engine="fallback_disabled")

        try:
            translated = self._call_nmt_pipeline(text, source_lang, target_lang)
            return TranslationResult(translated, source_lang, target_lang, fallback=False, engine="bhashini")

        except Exception as e:
            # Never crash the assessment over a translation hiccup,
            # and never invent a translation -- log clearly and
            # fall back to the original text.
            logger.exception(
                "Bhashini translation failed (%s -> %s): %r. "
                "Falling back to original text.",
                source_lang, target_lang, e,
            )
            return TranslationResult(text, source_lang, target_lang, fallback=True, engine="fallback_error")

    def translate_batch_from_english(self, texts, target_lang):
        """
        Convenience helper: translate a list of independent text
        fields (e.g. summary, risks[], recommended_verification[])
        from English to target_lang, each with its own fallback
        behavior. Order-preserving.
        """
        return [self.translate_from_english(t, target_lang) for t in texts]

    # -----------------------------------------------------
    # SPEECH (interface + fallback only -- Phase 2)
    # -----------------------------------------------------

    def speech_to_text(self, audio_bytes: bytes, source_lang: str) -> TranslationResult:
        """
        FUTURE SCOPE. Not called anywhere in v1 -- Streamlit
        only collects typed text input. Interface kept here so
        Phase 2 (voice input) only needs a Streamlit mic widget
        + this one method filled in with the ASR pipeline task,
        no architecture change.
        """
        raise NotImplementedError(
            "speech_to_text() is a Phase 2 feature; not wired "
            "into the v1 flow."
        )

    def text_to_speech(self, text: str, target_lang: str) -> bytes:
        """
        FUTURE SCOPE. Same status as speech_to_text().
        """
        raise NotImplementedError(
            "text_to_speech() is a Phase 2 feature; not wired "
            "into the v1 flow."
        )


# Module-level singleton -- cheap to construct, reused everywhere.
bhashini_service = BhashiniService()