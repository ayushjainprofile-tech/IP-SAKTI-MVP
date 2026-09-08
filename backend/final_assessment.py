"""
IP-SAKTI FINAL ASSESSMENT UI
--------------------------------
This is a separate Streamlit file for the "rest of the process":

Conversation completed
        ↓
Build ProductInput
        ↓
POST /api/analyze
        ↓
Show Classification
        ↓
Show IP / TK / ABS routing
        ↓
Show Evidence
        ↓
Validate supported/unsupported domains
        ↓
Show Confidence + Action Plan
        ↓
Safe escalation / disclaimer

Run:
    streamlit run final_assessment.py

Backend:
    http://127.0.0.1:8000
"""

import json
import requests
import streamlit as st


# =========================================================
# CONFIG
# =========================================================

import os
BACKEND_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:8001")
ANALYZE_URL = f"{BACKEND_URL}/api/analyze"

st.set_page_config(
    page_title="IP-SAKTI — Final Assessment",
    page_icon="⚖️",
    layout="wide",
)


# =========================================================
# HELPERS
# =========================================================

def parse_ingredients(value):
    """Convert conversation answer into ProductInput list."""
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]

    text = str(value or "").strip()

    if not text:
        return []

    # Conversation currently accepts comma-separated ingredients.
    return [
        item.strip()
        for item in text.split(",")
        if item.strip()
    ]


def build_product_input(answers):
    """Map conversation answers → /api/analyze ProductInput."""
    return {
        "product_name": str(
            answers.get("product_name", "")
        ).strip(),

        "ingredients": parse_ingredients(
            answers.get("ingredients", "")
        ),

        "purpose": str(
            answers.get("purpose", "")
        ).strip(),

        "product_type": str(
            answers.get("product_type", "")
        ).strip(),

        "jurisdiction": str(
            answers.get("jurisdiction", "")
        ).strip(),

        "based_on_traditional_knowledge": str(
            answers.get(
                "based_on_traditional_knowledge",
                ""
            )
        ).strip().lower(),
    }


def extract_answers_from_history(history):
    """
    Convert the existing Streamlit conversation history into
    the dictionary expected by ProductInput.

    This supports the question text used by conversation.py.
    """
    mapping = {}

    for item in history:
        question = item.get("question", "")
        answer = item.get("answer", "")

        if question == "What is the name of your product?":
            mapping["product_name"] = answer

        elif question == "What are the main ingredients in the product?":
            mapping["ingredients"] = answer

        elif question == "What is the purpose or intended use of the product?":
            mapping["purpose"] = answer

        elif question.startswith(
            "What type of product is it?"
        ):
            mapping["product_type"] = answer

        elif question.startswith(
            "Which country or jurisdiction"
        ):
            mapping["jurisdiction"] = answer

        elif question.startswith(
            "Is the product based on traditional knowledge?"
        ):
            mapping["based_on_traditional_knowledge"] = answer

    return mapping


def domain_status(result):
    validation = result.get("validation", {})
    supported = validation.get("supported_domains", [])
    unsupported = validation.get("unsupported_domains", [])

    return supported, unsupported


def safe_get(data, *keys, default=None):
    current = data

    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key)

    return current if current is not None else default


# =========================================================
# HEADER
# =========================================================

st.title("⚖️ IP-SAKTI")
st.subheader("Final IP / Traditional Knowledge / ABS Assessment")

st.caption(
    "Conversation → ProductInput → Evidence Retrieval → "
    "Validation → Grounded Assessment"
)

st.info(
    "This screen connects the completed questionnaire to the "
    "existing FastAPI /api/analyze endpoint. It does not make "
    "a legal determination."
)


# =========================================================
# SESSION STATE
# =========================================================

if "final_answers" not in st.session_state:
    st.session_state.final_answers = {}

if "analysis_result" not in st.session_state:
    st.session_state.analysis_result = None


# =========================================================
# INPUT OPTIONS
# =========================================================

st.markdown("## 1. Product information")

history = st.session_state.get("history", [])

if history:
    auto_answers = extract_answers_from_history(history)

    if auto_answers:
        st.session_state.final_answers.update(auto_answers)

    st.success(
        "Conversation history detected. ProductInput was built automatically."
    )

answers = st.session_state.final_answers

product_name = st.text_input(
    "Product name",
    value=answers.get("product_name", ""),
)

ingredients_text = st.text_input(
    "Ingredients (comma separated)",
    value=answers.get("ingredients", ""),
)

purpose = st.text_area(
    "Purpose / intended use",
    value=answers.get("purpose", ""),
)

product_type = st.text_input(
    "Product type",
    value=answers.get("product_type", ""),
)

jurisdiction = st.text_input(
    "Jurisdiction",
    value=answers.get("jurisdiction", ""),
)

tk_value = st.selectbox(
    "Based on traditional knowledge?",
    options=["yes", "no"],
    index=0
    if str(
        answers.get(
            "based_on_traditional_knowledge",
            "yes",
        )
    ).lower()
    == "yes"
    else 1,
)


# =========================================================
# PRODUCT INPUT PREVIEW
# =========================================================

product_input = build_product_input(
    {
        "product_name": product_name,
        "ingredients": ingredients_text,
        "purpose": purpose,
        "product_type": product_type,
        "jurisdiction": jurisdiction,
        "based_on_traditional_knowledge": tk_value,
    }
)

with st.expander("View ProductInput sent to backend"):
    st.json(product_input)


# =========================================================
# VALIDATION
# =========================================================

missing = []

for field in [
    "product_name",
    "purpose",
    "product_type",
    "jurisdiction",
]:
    if not product_input[field]:
        missing.append(field)

if not product_input["ingredients"]:
    missing.append("ingredients")


# =========================================================
# RUN ANALYSIS
# =========================================================

st.markdown("## 2. Run IP-SAKTI analysis")

if missing:
    st.warning(
        "Missing required information: "
        + ", ".join(missing)
    )

if st.button(
    "🔎 Analyze Product",
    type="primary",
    use_container_width=True,
):
    if missing:
        st.error(
            "Please complete the missing fields before analysis."
        )
    else:
        try:
            with st.spinner(
                "Running classification, domain routing, retrieval and validation..."
            ):
                response = requests.post(
                    ANALYZE_URL,
                    json=product_input,
                    timeout=120,
                )

            if not response.ok:
                st.error(
                    f"Backend returned HTTP {response.status_code}"
                )

                try:
                    st.json(response.json())
                except Exception:
                    st.code(response.text)

            else:
                st.session_state.analysis_result = response.json()
                st.success(
                    "Analysis completed successfully."
                )

        except requests.exceptions.RequestException as exc:
            st.error(
                "Could not connect to the FastAPI backend."
            )
            st.code(str(exc))


# =========================================================
# RESULT
# =========================================================

result = st.session_state.analysis_result

if result:
    st.divider()
    st.markdown("## 3. Final assessment")

    # -----------------------------------------------------
    # TOP SUMMARY
    # -----------------------------------------------------

    classification = result.get(
        "classification",
        {},
    )

    domains = result.get(
        "domains",
        [],
    )

    confidence = result.get(
        "confidence",
        {},
    )

    validation = result.get(
        "validation",
        {},
    )

    supported, unsupported = domain_status(result)

    c1, c2, c3, c4 = st.columns(4)

    with c1:
        st.metric(
            "Product Type",
            classification.get(
                "product_type",
                product_type,
            ),
        )

    with c2:
        st.metric(
            "TK Status",
            classification.get(
                "traditional_knowledge_status",
                "N/A",
            ),
        )

    with c3:
        st.metric(
            "Domains Detected",
            len(domains),
        )

    with c4:
        st.metric(
            "Confidence",
            str(
                confidence.get(
                    "level",
                    "N/A",
                )
            ).upper(),
        )

    # -----------------------------------------------------
    # ROUTING
    # -----------------------------------------------------

    st.markdown("### Domain routing")

    route_cols = st.columns(3)

    for idx, domain in enumerate(
        ["IP", "TK", "ABS"]
    ):
        with route_cols[idx]:
            if domain in supported:
                st.success(
                    f"✅ {domain} — evidence supported"
                )
            elif domain in unsupported:
                st.warning(
                    f"⚠️ {domain} — evidence not established"
                )
            else:
                st.info(
                    f"ℹ️ {domain} — not detected"
                )

    st.caption(
        "Important: detected domain ≠ proven legal issue. "
        "The validation layer decides which domains actually "
        "have supporting evidence."
    )

    # -----------------------------------------------------
    # VALIDATION
    # -----------------------------------------------------

    st.markdown("### Evidence validation")

    v1, v2, v3, v4 = st.columns(4)

    with v1:
        st.metric(
            "Evidence",
            validation.get(
                "evidence_count",
                len(result.get("evidence", [])),
            ),
        )

    with v2:
        st.metric(
            "Strong evidence",
            validation.get(
                "strong_evidence_count",
                0,
            ),
        )

    with v3:
        st.metric(
            "Domain aligned",
            validation.get(
                "domain_aligned_count",
                0,
            ),
        )

    with v4:
        st.metric(
            "Ingredient evidence",
            validation.get(
                "ingredient_evidence_count",
                0,
            ),
        )

    validation_message = validation.get(
        "message",
        "",
    )

    if validation.get("status") == "PARTIAL":
        st.warning(validation_message)
    elif validation.get("status") == "PASS":
        st.success(validation_message)
    else:
        st.info(
            validation_message
            or "Review validation details below."
        )

    # -----------------------------------------------------
    # CLASSIFICATION NOTE
    # -----------------------------------------------------

    st.markdown("### Classification")

    st.write(
        classification.get(
            "classification_note",
            "No classification note returned.",
        )
    )

    # -----------------------------------------------------
    # SUPPORTED / UNSUPPORTED
    # -----------------------------------------------------

    left, right = st.columns(2)

    with left:
        st.markdown("#### Supported domains")
        if supported:
            for domain in supported:
                st.success(domain)
        else:
            st.write("None established by retrieved evidence.")

    with right:
        st.markdown("#### Unsupported domains")
        if unsupported:
            for domain in unsupported:
                st.warning(domain)
        else:
            st.write("None.")

    # -----------------------------------------------------
    # EVIDENCE
    # -----------------------------------------------------

    st.markdown("### Retrieved evidence")

    evidence = result.get(
        "evidence",
        [],
    )

    if not evidence:
        st.warning(
            "No evidence was returned. The system should abstain "
            "from making a substantive conclusion."
        )
    else:
        for index, item in enumerate(evidence, start=1):
            title = (
                f"{index}. "
                f"{item.get('domain', 'UNKNOWN')} — "
                f"{item.get('source', 'Unknown source')}"
            )

            with st.expander(title):
                ec1, ec2, ec3 = st.columns(3)

                with ec1:
                    st.write(
                        "**Score:**",
                        item.get("score"),
                    )

                with ec2:
                    st.write(
                        "**Retrieval:**",
                        item.get("retrieval_type"),
                    )

                with ec3:
                    st.write(
                        "**Quality:**",
                        item.get("evidence_quality"),
                    )

                if item.get("matched_terms"):
                    st.write(
                        "**Matched terms:**",
                        ", ".join(
                            item.get(
                                "matched_terms",
                                [],
                            )
                        ),
                    )

                if item.get("ingredient_matches"):
                    st.write(
                        "**Ingredient matches:**",
                        ", ".join(
                            item.get(
                                "ingredient_matches",
                                [],
                            )
                        ),
                    )

                st.write(
                    item.get(
                        "text",
                        "No evidence text returned.",
                    )
                )

    # -----------------------------------------------------
    # CONFIDENCE
    # -----------------------------------------------------

    st.markdown("### Confidence")

    confidence_level = confidence.get(
        "level",
        "UNKNOWN",
    )

    confidence_score = confidence.get(
        "score",
        None,
    )

    if confidence_level.upper() == "HIGH":
        st.success(
            f"Confidence: {confidence_level}"
            + (
                f" ({confidence_score})"
                if confidence_score is not None
                else ""
            )
        )
    elif confidence_level.upper() == "MEDIUM":
        st.warning(
            f"Confidence: {confidence_level}"
            + (
                f" ({confidence_score})"
                if confidence_score is not None
                else ""
            )
        )
    else:
        st.error(
            f"Confidence: {confidence_level}"
            + (
                f" ({confidence_score})"
                if confidence_score is not None
                else ""
            )
        )

    basis = confidence.get(
        "basis",
        [],
    )

    if basis:
        st.write("**Confidence basis:**")
        for item in basis:
            st.write(f"• {item}")

    if confidence.get("warning"):
        st.caption(
            confidence["warning"]
        )

    # -----------------------------------------------------
    # ACTION PLAN
    # -----------------------------------------------------

    st.markdown("### Action plan")

    action_plan = result.get(
        "action_plan",
        [],
    )

    if action_plan:
        for step_no, action in enumerate(
            action_plan,
            start=1,
        ):
            st.write(
                f"**{step_no}.** {action}"
            )
    else:
        st.info(
            "No action plan was returned by the backend."
        )

    # -----------------------------------------------------
    # LLM REASONING
    # -----------------------------------------------------

    st.markdown("### AI interpretation")

    llm_reasoning = result.get(
        "llm_reasoning",
        {},
    )

    if llm_reasoning:
        st.write(
            "**Status:**",
            llm_reasoning.get(
                "status",
                "N/A",
            ),
        )

        analysis = llm_reasoning.get(
            "analysis",
            {},
        )

        st.write(
            analysis.get(
                "summary",
                "No summary returned.",
            )
        )

        if analysis.get("risks"):
            st.write("**Risks identified:**")
            for risk in analysis["risks"]:
                st.warning(risk)

        if analysis.get(
            "recommended_verification"
        ):
            st.write(
                "**Recommended verification:**"
            )

            for item in analysis[
                "recommended_verification"
            ]:
                st.write(
                    f"• {item}"
                )

        if analysis.get("limitations"):
            st.caption(
                "Limitations: "
                + str(
                    analysis["limitations"]
                )
            )

    # -----------------------------------------------------
    # SEARCH QUERY
    # -----------------------------------------------------

    with st.expander("View retrieval query"):
        st.code(
            result.get(
                "search_query",
                "",
            )
        )

    # -----------------------------------------------------
    # RAW RESPONSE
    # -----------------------------------------------------

    with st.expander("View raw /api/analyze response"):
        st.json(result)

    # -----------------------------------------------------
    # SAFE DECISION
    # -----------------------------------------------------

    st.markdown("## 4. Safe decision")

    if unsupported or not evidence:
        st.warning(
            "⚠️ Evidence is incomplete. IP-SAKTI should NOT "
            "infer unsupported TK/ABS/IP conclusions. "
            "Escalate the unresolved issue for human verification."
        )
    else:
        st.success(
            "Evidence was retrieved and validated for the "
            "supported domain(s). The result remains an "
            "information/routing signal, not a legal determination."
        )

    st.info(
        "⚖️ IP-SAKTI provides information and evidence-grounded "
        "routing. It is not a substitute for advice from a "
        "qualified IP/TK/ABS professional."
    )


# =========================================================
# RESET
# =========================================================

st.divider()

if st.button(
    "🔄 Clear analysis",
    use_container_width=True,
):
    st.session_state.analysis_result = None
    st.rerun()
