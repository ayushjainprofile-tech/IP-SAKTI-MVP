import os
import requests
import streamlit as st


# =========================================================
# CONFIG
# =========================================================

BACKEND_URL = os.getenv(
    "IP_SAKTI_BACKEND_URL",
    "http://127.0.0.1:8000",
).rstrip("/")

LANGUAGE_URL = f"{BACKEND_URL}/api/language"

REQUEST_TIMEOUT = 60
ANALYSIS_TIMEOUT = 300

LANGUAGE_OPTIONS = {
    "English": "en",
    "हिंदी": "hi",
    "मराठी": "mr",
}

JURISDICTION_OPTIONS = {
    "India": "India",
    "International": "International",
}

DOMAIN_INFO = {
    "IP": ("Intellectual Property", "📜"),
    "TK": ("Traditional Knowledge", "🌿"),
    "ABS": ("Access & Benefit Sharing", "🤝"),
}


# =========================================================
# PAGE
# =========================================================

st.set_page_config(
    page_title="IP-SAKTI",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    .block-container {
        padding-top: 1.5rem;
        padding-bottom: 2rem;
    }
    .small-muted {
        color: #6b7280;
        font-size: 0.88rem;
    }
    .risk-box {
        border-left: 4px solid #f59e0b;
        padding: 0.65rem 0.9rem;
        margin: 0.45rem 0;
        border-radius: 0.35rem;
        background: rgba(245, 158, 11, 0.08);
    }
    .evidence-box {
        border-left: 4px solid #2563eb;
        padding: 0.65rem 0.9rem;
        margin: 0.45rem 0;
        border-radius: 0.35rem;
        background: rgba(37, 99, 235, 0.06);
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# =========================================================
# SESSION STATE
# =========================================================

DEFAULTS = {
    "session_id": None,
    "question": None,
    "history": [],
    "completed": False,
    "analysis": None,
    "analyzing": False,
    "language": "en",
    "jurisdiction": "India",
}

for key, value in DEFAULTS.items():
    if key not in st.session_state:
        st.session_state[key] = value


# =========================================================
# LANGUAGE / BHASHINI LAYER
# =========================================================

def translate_text(text, source_lang, target_lang):
    """
    Thin frontend client for the backend language service.

    Translation failure must never break the assessment.
    Retrieval, evidence validation and reasoning remain backend concerns.
    """
    if not text or source_lang == target_lang:
        return text

    try:
        response = requests.post(
            f"{LANGUAGE_URL}/translate",
            json={
                "text": text,
                "source_lang": source_lang,
                "target_lang": target_lang,
            },
            timeout=15,
        )
        response.raise_for_status()
        return response.json().get("text", text)
    except Exception:
        return text


def translate_analysis_for_display(analysis, target_lang):
    """
    Translate narrative analysis fields only.

    Evidence text, source identifiers, page numbers and citations should
    remain attached to the original authoritative sources.
    """
    if target_lang == "en":
        return analysis

    try:
        response = requests.post(
            f"{LANGUAGE_URL}/translate-analysis",
            json={
                "analysis": analysis,
                "target_lang": target_lang,
            },
            timeout=30,
        )
        response.raise_for_status()
        return response.json()
    except Exception:
        return analysis


def ui_text(english, hindi=None, marathi=None):
    """Small UI-label helper; the backend remains the source of truth."""
    lang = st.session_state.language
    if lang == "hi" and hindi:
        return hindi
    if lang == "mr" and marathi:
        return marathi
    return english


# =========================================================
# QUESTION / BACKEND HELPERS
# =========================================================

def normalize_question(data):
    if not isinstance(data, dict):
        data = {}

    question = data.get("question")
    if not isinstance(question, str):
        question = ""

    question_number = data.get(
        "question_number",
        len(st.session_state.history) + 1,
    )

    total_questions = data.get(
        "total_questions",
        6,
    )

    return {
        **data,
        "question": question.strip(),
        "question_number": question_number,
        "total_questions": total_questions,
        "completed": bool(data.get("completed", False)),
    }


def get_next_question(session_id):
    response = requests.get(
        f"{BACKEND_URL}/api/conversation/{session_id}/next",
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    return normalize_question(response.json())


def start_assessment():
    # Preserve the existing /api/conversation/start contract.
    response = requests.post(
        f"{BACKEND_URL}/api/conversation/start",
        json={},
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()

    data = response.json()
    session_id = data.get("session_id")

    if not session_id:
        raise RuntimeError(f"No session_id returned: {data}")

    question = normalize_question(data)

    if not question["question"]:
        question = get_next_question(session_id)

    return session_id, question


def submit_answer(session_id, answer):
    # Preserve the existing /api/conversation/answer contract.
    response = requests.post(
        f"{BACKEND_URL}/api/conversation/answer",
        json={
            "session_id": session_id,
            "answer": answer,
        },
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()

    data = response.json()

    if data.get("completed"):
        return {
            "completed": True,
            "answers": data.get("answers", {}),
        }

    question = normalize_question(data)

    if not question["question"]:
        question = get_next_question(session_id)

    return question


# =========================================================
# PRODUCT INPUT EXTRACTION
# =========================================================

def extract_product_input():
    answers = st.session_state.history

    if not answers:
        raise RuntimeError("No questionnaire answers were collected.")

    product_name = ""
    purpose = ""
    product_type = "unknown"
    ingredients = []
    traditional_knowledge = "no"

    for item in answers:
        if not isinstance(item, dict):
            continue

        question = str(item.get("question", "")).lower().strip()
        answer = str(item.get("answer", "")).strip()

        if (
            "product name" in question
            or "name of your product" in question
            or "name of the product" in question
            or "what is the product" in question
        ):
            product_name = answer

        elif (
            "purpose" in question
            or "intended use" in question
            or "what is it used for" in question
            or "used for" in question
            or "use of the product" in question
        ):
            purpose = answer

        elif (
            "product type" in question
            or "type of product" in question
            or "product category" in question
            or "category of product" in question
            or "category" in question
        ):
            product_type = answer

        elif (
            "ingredient" in question
            or "ingredients" in question
            or "contains" in question
            or "composition" in question
        ):
            ingredients = [
                ingredient.strip()
                for ingredient in answer.replace(";", ",").split(",")
                if ingredient.strip()
            ]

        elif (
            "traditional knowledge" in question
            or "traditional practice" in question
            or "traditional use" in question
            or "ayurveda" in question
        ):
            normalized = answer.lower().strip()

            if normalized in {"yes", "y", "true"}:
                traditional_knowledge = "yes"
            elif normalized in {"no", "n", "false"}:
                traditional_knowledge = "no"

    if not product_name:
        product_name = "Unknown Product"

    if not purpose:
        purpose = "Purpose not explicitly provided during questionnaire."

    if not product_type:
        product_type = "unknown"

    return {
        "product_name": product_name,
        "ingredients": ingredients,
        "purpose": purpose,
        "product_type": product_type,
        "jurisdiction": st.session_state.jurisdiction,
        "based_on_traditional_knowledge": traditional_knowledge,
    }


def run_analysis():
    """
    Send the completed questionnaire to /api/analyze.

    The backend remains responsible for classification, routing, retrieval,
    evidence validation, RAG/LLM reasoning and safe decision making.
    """
    payload = extract_product_input()

    with st.expander(
        ui_text(
            "🔧 Analysis request sent to backend",
            "🔧 बैकएंड को भेजा गया विश्लेषण अनुरोध",
            "🔧 बॅकएंडला पाठवलेली विश्लेषण विनंती",
        ),
        expanded=False,
    ):
        st.json(payload)

    try:
        response = requests.post(
            f"{BACKEND_URL}/api/analyze",
            json=payload,
            timeout=ANALYSIS_TIMEOUT,
        )
    except requests.exceptions.Timeout as exc:
        raise requests.exceptions.Timeout(
            f"The IP-SAKTI analysis request exceeded the "
            f"{ANALYSIS_TIMEOUT}-second timeout. "
            "The backend may still be processing the analysis."
        ) from exc

    if response.status_code == 422:
        try:
            validation_details = response.json()
        except ValueError:
            validation_details = response.text

        st.error("❌ Backend validation failed (HTTP 422).")
        st.json(validation_details)

        error = requests.exceptions.HTTPError(
            "HTTP 422 returned by /api/analyze."
        )
        error.response = response
        raise error

    response.raise_for_status()

    try:
        return response.json()
    except ValueError as exc:
        raise RuntimeError(
            "The backend returned HTTP 200, but the response was not valid JSON."
        ) from exc


def reset_assessment():
    for key, value in DEFAULTS.items():
        st.session_state[key] = value


# =========================================================
# HEADER
# =========================================================

st.title("⚖️ IP-SAKTI")
st.subheader(
    ui_text(
        "Evidence-First IP / Traditional Knowledge / ABS Assessment",
        "साक्ष्य-आधारित IP / पारंपरिक ज्ञान / ABS मूल्यांकन",
        "पुराव्यावर आधारित IP / पारंपरिक ज्ञान / ABS मूल्यांकन",
    )
)

st.caption(
    "Evidence-grounded assessment for Intellectual Property, "
    "Traditional Knowledge and Access & Benefit Sharing."
)


# =========================================================
# GLOBAL CONTROLS
# =========================================================

control1, control2 = st.columns(2)

with control1:
    selected_language_label = st.selectbox(
        "🌐 Language",
        options=list(LANGUAGE_OPTIONS.keys()),
        index=list(LANGUAGE_OPTIONS.values()).index(
            st.session_state.language
        ),
    )
    st.session_state.language = LANGUAGE_OPTIONS[selected_language_label]

with control2:
    selected_jurisdiction_label = st.selectbox(
        "⚖️ Jurisdiction",
        options=list(JURISDICTION_OPTIONS.keys()),
        index=list(JURISDICTION_OPTIONS.values()).index(
            st.session_state.jurisdiction
        ),
    )
    st.session_state.jurisdiction = JURISDICTION_OPTIONS[
        selected_jurisdiction_label
    ]

if st.session_state.language != "en":
    st.info(
        ui_text(
            "Questions and narrative results may be translated through the "
            "language service. Original evidence, source names, page numbers "
            "and citations remain unchanged.",
            "प्रश्न और विश्लेषण भाषा सेवा के माध्यम से अनुवादित हो सकते हैं। "
            "मूल साक्ष्य, स्रोत नाम, पृष्ठ संख्या और उद्धरण अपरिवर्तित रहते हैं।",
            "प्रश्न आणि विश्लेषण भाषा सेवेद्वारे अनुवादित होऊ शकतात. "
            "मूळ पुरावे, स्रोतांची नावे, पृष्ठ क्रमांक आणि उद्धरणे बदलली जात नाहीत.",
        )
    )

st.caption(
    f"Current jurisdiction: **{st.session_state.jurisdiction}**"
)


# =========================================================
# START
# =========================================================

if st.session_state.session_id is None:
    st.info(
        ui_text(
            "Start an assessment to classify your product and analyse "
            "relevant IP / TK / ABS evidence.",
            "अपने उत्पाद को वर्गीकृत करने और संबंधित IP / TK / ABS "
            "साक्ष्य का विश्लेषण करने के लिए मूल्यांकन शुरू करें।",
            "तुमच्या उत्पादनाचे वर्गीकरण आणि संबंधित IP / TK / ABS "
            "पुराव्याचे विश्लेषण करण्यासाठी मूल्यांकन सुरू करा.",
        )
    )

    if st.button(
        ui_text(
            "🚀 Start Assessment",
            "🚀 मूल्यांकन शुरू करें",
            "🚀 मूल्यांकन सुरू करा",
        ),
        use_container_width=True,
        type="primary",
    ):
        try:
            session_id, question = start_assessment()

            st.session_state.session_id = session_id
            st.session_state.question = question
            st.session_state.history = []
            st.session_state.completed = False
            st.session_state.analysis = None
            st.rerun()

        except Exception as exc:
            st.error("Could not start assessment.")
            st.exception(exc)


# =========================================================
# QUESTIONNAIRE
# =========================================================

if (
    st.session_state.session_id
    and not st.session_state.completed
):
    question_data = st.session_state.question

    if question_data:
        number = question_data.get(
            "question_number",
            len(st.session_state.history) + 1,
        )
        total = question_data.get("total_questions", 6)

        question_en = question_data.get("question", "")
        display_question = translate_text(
            question_en,
            "en",
            st.session_state.language,
        )

        st.progress(
            min(
                max(float(number) / max(float(total), 1), 0.0),
                1.0,
            )
        )

        st.caption(
            ui_text(
                f"Question {number} of {total}",
                f"प्रश्न {number} / {total}",
                f"प्रश्न {number} / {total}",
            )
        )

        st.markdown(f"### {display_question}")

        answer = st.text_input(
            ui_text(
                "Your answer",
                "आपका उत्तर",
                "तुमचे उत्तर",
            ),
            key=f"answer_{number}",
        )

        if st.button(
            ui_text(
                "Next →",
                "अगला →",
                "पुढे →",
            ),
            use_container_width=True,
        ):
            if not answer.strip():
                st.warning(
                    ui_text(
                        "Please enter an answer.",
                        "कृपया उत्तर दर्ज करें।",
                        "कृपया उत्तर द्या.",
                    )
                )
            else:
                try:
                    # Canonical English answer goes into the existing backend
                    # conversation and retrieval pipeline.
                    answer_en = translate_text(
                        answer.strip(),
                        st.session_state.language,
                        "en",
                    )

                    result = submit_answer(
                        st.session_state.session_id,
                        answer_en,
                    )

                    st.session_state.history.append(
                        {
                            "question": question_en,
                            "answer": answer_en,
                            "display_answer": answer.strip(),
                        }
                    )

                    if result.get("completed"):
                        st.session_state.completed = True
                    else:
                        st.session_state.question = result

                    st.rerun()

                except Exception as exc:
                    st.error("Could not submit answer.")
                    st.exception(exc)


# =========================================================
# COMPLETED → ANALYSIS
# =========================================================

if (
    st.session_state.session_id
    and st.session_state.completed
    and st.session_state.analysis is None
):
    st.success(
        ui_text(
            "✅ Questionnaire completed.",
            "✅ प्रश्नावली पूरी हुई।",
            "✅ प्रश्नावली पूर्ण झाली.",
        )
    )

    st.markdown("## 🔎 Ready for IP-SAKTI Analysis")

    st.write(
        "Your answers will be routed through product classification, "
        "jurisdiction routing, IP/TK/ABS retrieval, evidence validation "
        "and grounded reasoning."
    )

    with st.expander(
        ui_text(
            "View collected answers",
            "संग्रहित उत्तर देखें",
            "संकलित उत्तरे पहा",
        )
    ):
        for index, item in enumerate(
            st.session_state.history,
            start=1,
        ):
            st.markdown(f"**Q{index}:** {item.get('question', '')}")
            st.markdown(
                f"**A:** {item.get('display_answer', item.get('answer', ''))}"
            )
            st.divider()

    if st.button(
        "🔬 ANALYZE PRODUCT",
        type="primary",
        use_container_width=True,
    ):
        try:
            with st.spinner(
                "Running IP-SAKTI evidence analysis..."
            ):
                analysis = run_analysis()

                # Only narrative display fields are translated.
                analysis = translate_analysis_for_display(
                    analysis,
                    st.session_state.language,
                )

            st.session_state.analysis = analysis
            st.rerun()

        except requests.exceptions.Timeout as exc:
            st.error(
                f"⏱️ The analysis request timed out after "
                f"{ANALYSIS_TIMEOUT} seconds."
            )
            st.exception(exc)

        except requests.exceptions.HTTPError as exc:
            st.error("Analysis endpoint returned an error.")

            response = getattr(exc, "response", None)
            if response is not None:
                try:
                    st.json(response.json())
                except Exception:
                    st.code(response.text)

        except Exception as exc:
            st.error("Could not run analysis.")
            st.exception(exc)


# =========================================================
# ANALYSIS RESULT HELPERS
# =========================================================

def safe_score(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def render_classification(data):
    product = data.get("product") or {}
    classification = data.get("classification") or {}

    st.markdown("## 🧴 Product Classification")

    product_name = product.get(
        "product_name",
        data.get("product_name", "Unknown"),
    )

    product_type = classification.get(
        "product_type",
        product.get("product_type", "Unknown"),
    )

    jurisdiction = classification.get(
        "jurisdiction",
        product.get("jurisdiction", st.session_state.jurisdiction),
    )

    tk_status = classification.get(
        "traditional_knowledge_status",
        product.get("based_on_traditional_knowledge", "Unknown"),
    )

    cols = st.columns(4)

    cols[0].metric("Product", str(product_name))
    cols[1].metric("Type", str(product_type))
    cols[2].metric("Jurisdiction", str(jurisdiction))
    cols[3].metric("TK Based", str(tk_status))

    classification_confidence = classification.get("confidence")
    if classification_confidence is not None:
        st.metric(
            "Classification Confidence",
            str(classification_confidence),
        )

    reason = classification.get("reason")
    if reason:
        st.markdown("### Why this classification?")
        st.write(reason)

    required_verification = classification.get(
        "required_verification",
        classification.get("verification"),
    )
    if required_verification:
        st.markdown("### 🔎 Required Verification")
        if isinstance(required_verification, list):
            for item in required_verification:
                st.write(f"• {item}")
        else:
            st.write(required_verification)

    classification_evidence = classification.get("evidence")
    if classification_evidence:
        with st.expander("Classification Evidence"):
            if isinstance(classification_evidence, list):
                for item in classification_evidence:
                    st.write(item)
            else:
                st.write(classification_evidence)


def render_domains(data):
    domains = data.get("domains") or []

    supported_domains = data.get("supported_domains") or []
    unsupported_domains = data.get("unsupported_domains") or []

    domain_details = data.get("domain_details") or data.get(
        "domain_analysis",
        {},
    )

    st.markdown("## 🧭 Domain Routing")

    cols = st.columns(3)

    for index, (code, (name, icon)) in enumerate(DOMAIN_INFO.items()):
        details = (
            domain_details.get(code)
            if isinstance(domain_details, dict)
            else None
        )

        is_supported = code in supported_domains
        is_routed = code in domains

        if not supported_domains and not unsupported_domains:
            is_supported = is_routed

        if is_supported:
            cols[index].success(f"{icon} ✓ {name}")
        elif code in unsupported_domains:
            cols[index].warning(f"{icon} ⚠ {name} — insufficient evidence")
        elif is_routed:
            cols[index].info(f"{icon} • {name} — routed")
        else:
            cols[index].info(f"{icon} — {name} — not routed")

        if isinstance(details, dict):
            confidence = details.get("confidence")
            evidence_count = details.get(
                "evidence_count",
                len(details.get("evidence", []))
                if isinstance(details.get("evidence"), list)
                else None,
            )

            if confidence is not None:
                cols[index].caption(f"Confidence: {confidence}")
            if evidence_count is not None:
                cols[index].caption(
                    f"Evidence items: {evidence_count}"
                )

    if supported_domains:
        st.write(
            "**Supported domains:** "
            + ", ".join(map(str, supported_domains))
        )

    if unsupported_domains:
        st.write(
            "**Unsupported / uncertain domains:** "
            + ", ".join(map(str, unsupported_domains))
        )


def render_validation(data):
    validation = data.get("validation") or {}
    status = validation.get("status", "UNKNOWN")

    st.markdown("## 🛡 Evidence Validation")

    if status in {"EVIDENCE_FOUND", "SUPPORTED", "PASS", "VALID"}:
        st.success(f"✓ {status}")
    elif status in {"PARTIAL", "LOW_CONFIDENCE", "INSUFFICIENT"}:
        st.warning(f"⚠ {status}")
    elif status in {"ABSTAIN", "ABSTAINED", "NO_EVIDENCE"}:
        st.error(f"⛔ {status}")
    else:
        st.info(f"Status: {status}")

    message = validation.get("message")
    if message:
        st.write(message)

    for key, label in [
        ("relevance", "Relevance"),
        ("domain_alignment", "Domain Alignment"),
        ("authority", "Source Authority"),
        ("evidence_quality", "Evidence Quality"),
        ("citation_verification", "Citation Verification"),
        ("contradiction_status", "Contradiction Status"),
    ]:
        value = validation.get(key)
        if value is not None:
            st.caption(f"**{label}:** {value}")


def render_confidence(data):
    confidence = data.get("confidence") or {}

    score = safe_score(confidence.get("score", 0))
    level = confidence.get("level", "UNKNOWN")

    st.markdown("## 🎯 Evidence Confidence")

    if score is not None:
        normalized = min(max(score, 0.0), 1.0)

        st.metric(
            "Confidence",
            f"{normalized * 100:.0f}%",
        )
        st.progress(normalized)
    else:
        st.metric("Confidence", str(confidence.get("score", "N/A")))

    st.info(f"Evidence confidence level: **{level}**")

    st.caption(
        confidence.get(
            "warning",
            "This is evidence confidence, not legal certainty.",
        )
    )


def render_evidence(data):
    evidence = data.get("evidence") or []

    st.markdown("## 📚 Retrieved Evidence")

    if not evidence:
        st.warning("No evidence was retrieved.")
        return

    st.caption(f"{len(evidence)} evidence item(s) returned.")

    for index, item in enumerate(evidence, start=1):
        if not isinstance(item, dict):
            st.write(item)
            continue

        source = item.get("source", "Unknown source")
        page = item.get("page", "N/A")
        score = item.get("score", 0)
        domain = item.get("domain", "Unknown")
        matched = item.get("matched_terms") or []

        with st.expander(
            f"Evidence {index} — {domain} — {source} — Page {page}"
        ):
            e1, e2, e3 = st.columns(3)

            e1.metric("Domain", str(domain))
            e2.metric("Page", str(page))
            e3.metric("Evidence Score", str(score))

            if matched:
                st.write(
                    "**Matched terms:** "
                    + ", ".join(map(str, matched))
                )

            st.markdown("### Source Text")
            st.write(
                item.get(
                    "text",
                    "No text available.",
                )
            )

            citation = item.get("citation")
            citation_url = item.get("url") or item.get("source_url")

            if citation:
                st.markdown("### Citation")
                st.write(citation)

            if citation_url:
                st.markdown("### Source Link")
                st.markdown(
                    f"[Open source]({citation_url})"
                )

            st.caption(
                f"Original source: {source}, page {page}"
            )


def render_ai_assessment(data):
    llm = data.get("llm_reasoning") or {}

    st.markdown("## 🧠 AI Assessment")

    if llm.get("status") == "SUCCESS":
        analysis_obj = llm.get("analysis") or {}

        summary = analysis_obj.get("summary")
        if summary:
            st.info(summary)

        domain_analysis = analysis_obj.get(
            "domain_analysis",
            {},
        )

        if domain_analysis:
            st.markdown("### Domain Analysis")

            if isinstance(domain_analysis, dict):
                for domain, result in domain_analysis.items():
                    with st.expander(str(domain)):
                        st.write(result)
            else:
                st.write(domain_analysis)

        risks = analysis_obj.get("risks") or []

        if risks:
            st.markdown("### ⚠️ Risks")
            for risk in risks:
                st.warning(risk)

    else:
        st.warning(
            "LLM reasoning was not successfully generated. "
            "Do not treat missing LLM output as evidence."
        )


def render_action_plan(data):
    action_plan = data.get("action_plan") or []

    st.markdown("## 🚀 Recommended Action Plan")

    if action_plan:
        for index, action in enumerate(action_plan, start=1):
            st.markdown(f"**{index}.** {action}")
    else:
        st.info("No action plan was returned.")


def render_verification(data):
    verification = data.get("recommended_verification")

    if not verification:
        verification = data.get("verification")

    if not verification:
        verification = data.get("missing_information")

    if not verification:
        return

    st.markdown("## 🔎 What Should Be Verified?")

    if isinstance(verification, list):
        for item in verification:
            st.write(f"• {item}")
    elif isinstance(verification, dict):
        for key, value in verification.items():
            st.markdown(f"**{key}:**")
            st.write(value)
    else:
        st.write(verification)


def render_escalation(data):
    escalation = data.get("human_escalation")

    if escalation is None:
        escalation = data.get("escalation")

    if not escalation:
        return

    st.markdown("## 👤 Human Review")

    if isinstance(escalation, dict):
        recommended = escalation.get(
            "recommended",
            escalation.get("required", False),
        )

        if recommended is True:
            st.error("Human Review Recommended")
        elif recommended is False:
            st.success("Human Review Not Currently Flagged")
        else:
            st.info(str(recommended))

        reason = escalation.get("reason")
        if reason:
            st.write(f"**Reason:** {reason}")

        reviewer = escalation.get("suggested_reviewer")
        if reviewer:
            st.write(f"**Suggested reviewer:** {reviewer}")

    else:
        st.info(escalation)


def render_missing_and_risks(data):
    missing = data.get("missing_information")

    if missing:
        st.markdown("## 🧩 Missing Information")

        if isinstance(missing, list):
            for item in missing:
                st.write(f"• {item}")
        else:
            st.write(missing)
            
# =========================================================
# 🤖 AGENTIC AI CHAT
# =========================================================

CHAT_TIMEOUT = 120


def ask_ip_sakti_ai(query):

    response = requests.post(
        f"{BACKEND_URL}/api/agent/chat",
        json={
            "query": query,
            "jurisdiction": st.session_state.get(
                "jurisdiction",
                "India"
            ),
        },
        timeout=CHAT_TIMEOUT,
    )

    response.raise_for_status()

    return response.json()


# =========================================================
# ANALYSIS RESULTS
# =========================================================

if st.session_state.analysis:
    data = st.session_state.analysis

    st.success(
        ui_text(
            "✅ IP-SAKTI analysis completed.",
            "✅ IP-SAKTI विश्लेषण पूरा हुआ।",
            "✅ IP-SAKTI विश्लेषण पूर्ण झाले.",
        )
    )

    st.markdown("# 📊 Assessment Result")

    # High-level summary row
    top1, top2, top3 = st.columns(3)

    top1.metric(
        "Jurisdiction",
        str(
            (data.get("classification") or {}).get(
                "jurisdiction",
                st.session_state.jurisdiction,
            )
        ),
    )

    confidence = data.get("confidence") or {}
    confidence_level = confidence.get("level", "UNKNOWN")
    top2.metric(
        "Evidence Confidence",
        str(confidence_level),
    )

    validation_status = (data.get("validation") or {}).get(
        "status",
        "UNKNOWN",
    )
    top3.metric(
        "Validation",
        str(validation_status),
    )

    render_classification(data)
    render_domains(data)
    render_validation(data)
    render_confidence(data)
    render_evidence(data)
    render_ai_assessment(data)
    render_verification(data)
    render_missing_and_risks(data)
    render_action_plan(data)
    render_escalation(data)

    # =====================================================
    # SAFE DECISION SUMMARY
    # =====================================================

    safe_decision = data.get("safe_decision")

    if safe_decision:
        st.markdown("## 🛡 Safe Decision")

        if isinstance(safe_decision, dict):
            decision = safe_decision.get(
                "decision",
                safe_decision.get("status", "UNKNOWN"),
            )
            st.info(f"Decision state: **{decision}**")

            reason = safe_decision.get("reason")
            if reason:
                st.write(reason)

            next_step = safe_decision.get("next_step")
            if next_step:
                st.write(f"**Next step:** {next_step}")
        else:
            st.info(safe_decision)

    # =====================================================
    # DISCLAIMER
    # =====================================================

    st.divider()

    st.warning(
        "⚠️ IP-SAKTI provides evidence-grounded information and does not "
        "provide legal advice. Final legal, patent, TK or ABS decisions "
        "should be verified with an appropriate qualified professional "
        "or facilitator."
    )

    # =====================================================
    # RAW JSON
    # =====================================================

    with st.expander(
        "🔧 Developer: View complete API response"
    ):
        st.json(data)

    # =====================================================
    # NEW ASSESSMENT
    # =====================================================

    if st.button(
        "🔄 Start New Assessment",
        use_container_width=True,
    ):
        reset_assessment()
        st.rerun()


# =========================================================
# 🤖 ASK IP-SAKTI AI
# =========================================================

st.divider()

st.markdown("# 🤖 Ask IP-SAKTI AI")

st.caption(
    "Ask questions about IP, Traditional Knowledge, "
    "ABS, Ayurveda and related regulations."
)

if "chat_messages" not in st.session_state:
    st.session_state.chat_messages = []


# Show previous messages
for message in st.session_state.chat_messages:

    with st.chat_message(message["role"]):

        st.markdown(message["content"])

        if message["role"] == "assistant":

            trace = message.get("trace", [])

            if trace:

                with st.expander(
                    "🤖 Agent Execution Trace"
                ):

                    for step in trace:

                        if isinstance(step, dict):

                            agent = step.get(
                                "step",
                                step.get(
                                    "agent",
                                    "Agent"
                                )
                            )

                            status = step.get(
                                "status",
                                "completed"
                            )

                            st.write(
                                f"✓ **{agent}** — {status}"
                            )

                        else:

                            st.write(
                                f"✓ {step}"
                            )


# Chat input
user_query = st.chat_input(
    "Ask IP-SAKTI AI..."
)


if user_query:

    # User message
    st.session_state.chat_messages.append(
        {
            "role": "user",
            "content": user_query,
        }
    )

    with st.chat_message("user"):
        st.markdown(user_query)


    # Agent response
    with st.chat_message("assistant"):

        with st.spinner(
            "🤖 IP-SAKTI Agent is researching..."
        ):

            try:

                result = ask_ip_sakti_ai(
                    user_query
                )

                answer = result.get(
                    "answer",
                    result.get(
                        "response",
                        "No answer returned."
                    )
                )

                st.markdown(answer)


                # -----------------------------
                # AGENT TRACE
                # -----------------------------

                trace = result.get(
                    "trace",
                    result.get(
                        "agent_trace",
                        []
                    )
                )

                if trace:

                    with st.expander(
                        "🤖 Agent Execution Trace"
                    ):

                        for step in trace:

                            if isinstance(step, dict):

                                agent = step.get(
                                    "step",
                                    step.get(
                                        "agent",
                                        "Agent"
                                    )
                                )

                                status = step.get(
                                    "status",
                                    "completed"
                                )

                                st.write(
                                    f"✓ **{agent}** — {status}"
                                )

                            else:

                                st.write(
                                    f"✓ {step}"
                                )


                # -----------------------------
                # SOURCES
                # -----------------------------

                sources = result.get(
                    "sources",
                    result.get(
                        "citations",
                        []
                    )
                )

                if sources:

                    with st.expander(
                        "📚 Sources"
                    ):

                        for i, source in enumerate(
                            sources,
                            start=1
                        ):

                            if isinstance(source, dict):

                                title = source.get(
                                    "title",
                                    source.get(
                                        "source",
                                        f"Source {i}"
                                    )
                                )

                                st.markdown(
                                    f"**{i}. {title}**"
                                )

                                url = source.get("url")

                                if url:

                                    st.markdown(
                                        f"[Open source]({url})"
                                    )

                            else:

                                st.write(
                                    f"{i}. {source}"
                                )


                # -----------------------------
                # CONFIDENCE
                # -----------------------------

                confidence = result.get(
                    "confidence"
                )

                if confidence is not None:

                    st.caption(
                        f"🎯 Evidence confidence: "
                        f"**{confidence}**"
                    )


                # Save response
                st.session_state.chat_messages.append(
                    {
                        "role": "assistant",
                        "content": str(answer),
                        "trace": trace,
                    }
                )


            except Exception as e:

                error_message = (
                    "❌ Could not connect to "
                    "the IP-SAKTI Agent."
                )

                st.error(error_message)

                st.caption(str(e))

                st.session_state.chat_messages.append(
                    {
                        "role": "assistant",
                        "content": error_message,
                    }
                )


# Clear chat
if st.session_state.chat_messages:

    if st.button(
        "🗑️ Clear AI Chat"
    ):

        st.session_state.chat_messages = []

        st.rerun()




# =========================================================
# SIDEBAR
# =========================================================

with st.sidebar:
    st.header("⚙️ IP-SAKTI System")

    try:
        response = requests.get(
            f"{BACKEND_URL}/",
            timeout=5,
        )

        if response.ok:
            st.success("Backend: Connected")

            try:
                backend_data = response.json()

                st.caption(
                    "API Version: "
                    + str(
                        backend_data.get(
                            "version",
                            "Unknown",
                        )
                    )
                )
            except Exception:
                pass
        else:
            st.warning("Backend: Not Ready")

    except Exception:
        st.error("Backend: Offline")

    st.divider()

    st.write(f"API: `{BACKEND_URL}`")

    st.write(
        "Session: "
        + (
            "🟢 Active"
            if st.session_state.session_id
            else "⚪ None"
        )
    )

    st.write(
        f"Language: `{st.session_state.language}`"
    )

    st.write(
        f"Jurisdiction: `{st.session_state.jurisdiction}`"
    )

    st.divider()

    if st.session_state.session_id:
        st.caption("Assessment in progress / completed")

    st.caption("IP-SAKTI MVP → Hackathon-ready frontend")
    st.caption(
        "Evidence-grounded IP / TK / ABS assessment"
    )
