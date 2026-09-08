import streamlit as st
import requests


# =========================================================
# CONFIG
# =========================================================

import os
BACKEND_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:8001")
REQUEST_TIMEOUT = 60
ANALYSIS_TIMEOUT = 300


st.set_page_config(
    page_title="IP-SAKTI",
    page_icon="⚖️",
    layout="wide",
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
}

for key, value in DEFAULTS.items():
    if key not in st.session_state:
        st.session_state[key] = value


# =========================================================
# HELPERS
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

    return normalize_question(
        response.json()
    )


def start_assessment():

    response = requests.post(
        f"{BACKEND_URL}/api/conversation/start",
        json={},
        timeout=REQUEST_TIMEOUT,
    )

    response.raise_for_status()

    data = response.json()

    session_id = data.get("session_id")

    if not session_id:
        raise RuntimeError(
            f"No session_id returned: {data}"
        )

    question = normalize_question(data)

    if not question["question"]:
        question = get_next_question(
            session_id
        )

    return session_id, question


def submit_answer(
    session_id,
    answer,
):

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
        question = get_next_question(
            session_id
        )

    return question


def run_analysis(session_id):
    """
    Convert the completed questionnaire into the ProductInput expected
    by /api/analyze.

    The session_id is used only by the questionnaire flow. It is NOT sent
    as the /api/analyze payload.
    """

    # -----------------------------------------------------
    # Collect completed questionnaire answers
    # -----------------------------------------------------

    answers = st.session_state.history

    if not answers:
        raise RuntimeError(
            "No questionnaire answers were collected."
        )

    # -----------------------------------------------------
    # Default values
    # -----------------------------------------------------

    product_name = ""
    purpose = ""
    product_type = "unknown"
    jurisdiction = "India"
    ingredients = []
    traditional_knowledge = "no"

    # -----------------------------------------------------
    # Extract answers from questionnaire
    # -----------------------------------------------------

    for item in answers:
        if not isinstance(item, dict):
            continue

        question = str(
            item.get("question", "")
        ).lower().strip()

        answer = str(
            item.get("answer", "")
        ).strip()

        # Product name
        if (
            "product name" in question
            or "name of your product" in question
            or "name of the product" in question
            or "what is the product" in question
        ):
            product_name = answer

        # Purpose / intended use
        elif (
            "purpose" in question
            or "intended use" in question
            or "what is it used for" in question
            or "used for" in question
            or "use of the product" in question
        ):
            purpose = answer

        # Product type
        elif (
            "product type" in question
            or "type of product" in question
            or "product category" in question
            or "category of product" in question
            or "category" in question
        ):
            product_type = answer

        # Ingredients
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

        # Jurisdiction
        elif (
            "jurisdiction" in question
            or "country" in question
            or "country or jurisdiction" in question
            or "where will" in question
        ):
            # The current MVP is configured for India.
            # Keep the API payload jurisdiction as India.
            jurisdiction = "India"

        # Traditional Knowledge
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

    # -----------------------------------------------------
    # Safe fallbacks
    # -----------------------------------------------------

    if not product_name:
        product_name = "Unknown Product"

    if not purpose:
        purpose = (
            "Purpose not explicitly provided "
            "during questionnaire."
        )

    if not product_type:
        product_type = "unknown"

    # -----------------------------------------------------
    # Build the exact /api/analyze payload
    # -----------------------------------------------------

    payload = {
        "product_name": product_name,
        "ingredients": ingredients,
        "purpose": purpose,
        "product_type": product_type,
        "jurisdiction": "India",
        "based_on_traditional_knowledge": traditional_knowledge,
    }

    # -----------------------------------------------------
    # Show exactly what Streamlit sends
    # -----------------------------------------------------

    with st.expander(
        "🔧 Analysis request sent to backend",
        expanded=True,
    ):
        st.json(payload)

    # -----------------------------------------------------
    # Call IP-SAKTI analysis endpoint
    # -----------------------------------------------------

    try:
        response = requests.post(
            f"{BACKEND_URL}/api/analyze",
            json=payload,
            timeout=ANALYSIS_TIMEOUT,
        )
    except requests.exceptions.Timeout as e:
        raise requests.exceptions.Timeout(
            "The IP-SAKTI analysis request exceeded the "
            f"{ANALYSIS_TIMEOUT}-second timeout. The backend may still "
            "be processing the analysis. Check the backend terminal "
            "before retrying."
        ) from e

    # -----------------------------------------------------
    # Handle HTTP errors with useful backend details
    # -----------------------------------------------------

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
    except ValueError as e:
        raise RuntimeError(
            "The backend returned HTTP 200, but the response was not "
            "valid JSON."
        ) from e


def reset_assessment():

    for key, value in DEFAULTS.items():
        st.session_state[key] = value


# =========================================================
# HEADER
# =========================================================

st.title("⚖️ IP-SAKTI")

st.subheader(
    "IP / Traditional Knowledge Assessment"
)

st.caption(
    "Evidence-grounded assessment for Ayurveda, "
    "Traditional Knowledge, Intellectual Property "
    "and Access & Benefit Sharing."
)


# =========================================================
# START
# =========================================================

if st.session_state.session_id is None:

    st.info(
        "Start an assessment to classify your product "
        "and analyse relevant IP / TK / ABS evidence."
    )

    if st.button(
        "🚀 Start Assessment",
        use_container_width=True,
    ):

        try:

            session_id, question = start_assessment()

            st.session_state.session_id = session_id
            st.session_state.question = question
            st.session_state.history = []
            st.session_state.completed = False
            st.session_state.analysis = None

            st.rerun()

        except Exception as e:

            st.error(
                "Could not start assessment."
            )

            st.exception(e)


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

        total = question_data.get(
            "total_questions",
            6,
        )

        question = question_data.get(
            "question",
            "",
        )

        st.progress(
            min(
                number / total,
                1.0,
            )
        )

        st.caption(
            f"Question {number} of {total}"
        )

        st.markdown(
            f"### {question}"
        )

        answer = st.text_input(
            "Your answer",
            key=f"answer_{number}",
        )

        if st.button(
            "Next →",
            use_container_width=True,
        ):

            if not answer.strip():

                st.warning(
                    "Please enter an answer."
                )

            else:

                try:

                    result = submit_answer(
                        st.session_state.session_id,
                        answer.strip(),
                    )

                    st.session_state.history.append(
                        {
                            "question": question,
                            "answer": answer.strip(),
                        }
                    )

                    if result.get("completed"):

                        st.session_state.completed = True

                    else:

                        st.session_state.question = result

                    st.rerun()

                except Exception as e:

                    st.error(
                        "Could not submit answer."
                    )

                    st.exception(e)


# =========================================================
# COMPLETED → ANALYSIS
# =========================================================

if (
    st.session_state.session_id
    and st.session_state.completed
    and st.session_state.analysis is None
):

    st.success(
        "✅ Questionnaire completed."
    )

    st.markdown(
        "## 🔎 Ready for IP-SAKTI Analysis"
    )

    st.write(
        "Your answers will now be routed through "
        "classification, IP/TK/ABS retrieval, "
        "evidence validation and reasoning."
    )

    with st.expander(
        "View collected answers"
    ):

        for item in st.session_state.history:

            st.markdown(
                f"**Q:** {item['question']}"
            )

            st.markdown(
                f"**A:** {item['answer']}"
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

                analysis = run_analysis(
                    st.session_state.session_id
                )

            st.session_state.analysis = analysis

            st.rerun()

        except requests.exceptions.Timeout as e:

            st.error(
                "⏱️ The analysis request timed out after "
                f"{ANALYSIS_TIMEOUT} seconds. The backend may still be "
                "processing the request. Check the backend terminal for "
                "a successful /api/analyze response before retrying."
            )
            st.exception(e)

        except requests.exceptions.HTTPError as e:

            st.error(
                "Analysis endpoint returned an error."
            )

            response = getattr(
                e,
                "response",
                None,
            )

            if response is not None:

                try:
                    st.json(
                        response.json()
                    )
                except Exception:
                    st.code(
                        response.text
                    )

        except Exception as e:

            st.error(
                "Could not run analysis."
            )

            st.exception(e)


# =========================================================
# ANALYSIS RESULTS
# =========================================================

if st.session_state.analysis:

    data = st.session_state.analysis

    st.success(
        "✅ IP-SAKTI analysis completed."
    )

    st.markdown(
        "# 📊 Assessment Result"
    )

    # -----------------------------------------------------
    # PRODUCT
    # -----------------------------------------------------

    product = data.get(
        "product",
        {}
    )

    classification = data.get(
        "classification",
        {}
    )

    st.markdown(
        "## 🧴 Product Classification"
    )

    c1, c2, c3, c4 = st.columns(4)

    c1.metric(
        "Product",
        product.get(
            "product_name",
            "Unknown",
        ),
    )

    c2.metric(
        "Type",
        classification.get(
            "product_type",
            product.get(
                "product_type",
                "Unknown",
            ),
        ),
    )

    c3.metric(
        "Jurisdiction",
        classification.get(
            "jurisdiction",
            product.get(
                "jurisdiction",
                "Unknown",
            ),
        ),
    )

    c4.metric(
        "TK Based",
        classification.get(
            "traditional_knowledge_status",
            "Unknown",
        ),
    )

    # -----------------------------------------------------
    # DOMAINS
    # -----------------------------------------------------

    domains = data.get(
        "domains",
        []
    )

    st.markdown(
        "## 🧭 Domain Routing"
    )

    cols = st.columns(3)

    domain_names = [
        ("IP", "Intellectual Property"),
        ("TK", "Traditional Knowledge"),
        ("ABS", "Access & Benefit Sharing"),
    ]

    for index, (code, name) in enumerate(
        domain_names
    ):

        if code in domains:

            cols[index].success(
                f"✓ {name}"
            )

        else:

            cols[index].info(
                f"— {name}"
            )

    # -----------------------------------------------------
    # VALIDATION
    # -----------------------------------------------------

    validation = data.get(
        "validation",
        {}
    )

    status = validation.get(
        "status",
        "UNKNOWN",
    )

    st.markdown(
        "## 🛡 Evidence Validation"
    )

    if status == "EVIDENCE_FOUND":

        st.success(
            "✓ Relevant domain-specific evidence found"
        )

    else:

        st.warning(
            f"Status: {status}"
        )

    st.write(
        validation.get(
            "message",
            "",
        )
    )

    # -----------------------------------------------------
    # CONFIDENCE
    # -----------------------------------------------------

    confidence = data.get(
        "confidence",
        {}
    )

    score = confidence.get(
        "score",
        0,
    )

    level = confidence.get(
        "level",
        "UNKNOWN",
    )

    st.markdown(
        "## 🎯 Evidence Confidence"
    )

    st.metric(
        "Confidence",
        f"{score * 100:.0f}%"
        if isinstance(score, (int, float))
        else str(score),
    )

    st.progress(
        min(
            max(
                float(score),
                0.0,
            ),
            1.0,
        )
        if isinstance(score, (int, float))
        else 0
    )

    st.info(
        f"Evidence confidence level: **{level}**"
    )

    st.caption(
        confidence.get(
            "warning",
            "This is evidence confidence, "
            "not legal certainty.",
        )
    )

    # -----------------------------------------------------
    # EVIDENCE
    # -----------------------------------------------------

    evidence = data.get(
        "evidence",
        []
    )

    st.markdown(
        "## 📚 Retrieved Evidence"
    )

    if not evidence:

        st.warning(
            "No evidence was retrieved."
        )

    else:

        for index, item in enumerate(
            evidence,
            start=1,
        ):

            source = item.get(
                "source",
                "Unknown source",
            )

            page = item.get(
                "page",
                "N/A",
            )

            score = item.get(
                "score",
                0,
            )

            domain = item.get(
                "domain",
                "Unknown",
            )

            matched = item.get(
                "matched_terms",
                [],
            )

            with st.expander(
                f"Evidence {index} — {domain} — "
                f"{source} — Page {page}"
            ):

                e1, e2, e3 = st.columns(3)

                e1.metric(
                    "Domain",
                    domain,
                )

                e2.metric(
                    "Page",
                    page,
                )

                e3.metric(
                    "Evidence Score",
                    score,
                )

                if matched:

                    st.write(
                        "Matched terms:",
                        ", ".join(
                            map(
                                str,
                                matched,
                            )
                        ),
                    )

                st.markdown(
                    "### Source Text"
                )

                st.write(
                    item.get(
                        "text",
                        "No text available.",
                    )
                )

                st.caption(
                    "Source: "
                    f"{source}, page {page}"
                )

    # -----------------------------------------------------
    # LLM REASONING
    # -----------------------------------------------------

    llm = data.get(
        "llm_reasoning",
        {}
    )

    st.markdown(
        "## 🧠 AI Assessment"
    )

    if llm.get("status") == "SUCCESS":

        analysis_text = (
            llm
            .get("analysis", {})
            .get("summary")
        )

        if analysis_text:

            st.info(
                analysis_text
            )

        domain_analysis = (
            llm
            .get("analysis", {})
            .get("domain_analysis", {})
        )

        if domain_analysis:

            st.markdown(
                "### Domain Analysis"
            )

            for domain, result in domain_analysis.items():

                st.markdown(
                    f"**{domain}**"
                )

                st.write(result)

        risks = (
            llm
            .get("analysis", {})
            .get("risks", [])
        )

        if risks:

            st.markdown(
                "### ⚠️ Risks"
            )

            for risk in risks:

                st.warning(
                    risk
                )

    else:

        st.warning(
            "LLM reasoning was not successfully generated."
        )

    # -----------------------------------------------------
    # ACTION PLAN
    # -----------------------------------------------------

    action_plan = data.get(
        "action_plan",
        []
    )

    st.markdown(
        "## 🚀 Recommended Action Plan"
    )

    if action_plan:

        for index, action in enumerate(
            action_plan,
            start=1,
        ):

            st.markdown(
                f"**{index}.** {action}"
            )

    else:

        st.info(
            "No action plan was returned."
        )

    # -----------------------------------------------------
    # DISCLAIMER
    # -----------------------------------------------------

    st.divider()

    st.warning(
        "⚠️ IP-SAKTI provides evidence-grounded "
        "information and does not provide legal advice. "
        "Final legal, patent, TK or ABS decisions should "
        "be verified with an appropriate qualified "
        "professional or facilitator."
    )

    # -----------------------------------------------------
    # RAW JSON
    # -----------------------------------------------------

    with st.expander(
        "🔧 Developer: View complete API response"
    ):

        st.json(
            data
        )

    # -----------------------------------------------------
    # NEW ASSESSMENT
    # -----------------------------------------------------

    if st.button(
        "🔄 Start New Assessment",
        use_container_width=True,
    ):

        reset_assessment()
        st.rerun()


# =========================================================
# SIDEBAR
# =========================================================

with st.sidebar:

    st.header(
        "⚙️ IP-SAKTI System"
    )

    try:

        response = requests.get(
            f"{BACKEND_URL}/",
            timeout=5,
        )

        if response.ok:

            st.success(
                "Backend: Connected"
            )

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

            st.warning(
                "Backend: Not Ready"
            )

    except Exception:

        st.error(
            "Backend: Offline"
        )

    st.divider()

    st.write(
        f"API: `{BACKEND_URL}`"
    )

    st.write(
        "Session: "
        + (
            "🟢 Active"
            if st.session_state.session_id
            else "⚪ None"
        )
    )

    st.divider()

    st.caption(
        "IP-SAKTI MVP"
    )

    st.caption(
        "Evidence-grounded IP / TK / ABS assessment"
    )