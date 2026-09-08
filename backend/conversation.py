"""
IP-SAKTI Conversation Manager

Handles the one-by-one question flow for the MVP.

The system collects:
1. Product name
2. Ingredients
3. Purpose
4. Product type
5. Jurisdiction
6. Traditional knowledge status
"""

from __future__ import annotations

from typing import Dict, Any
import uuid


# =========================================================
# QUESTION DEFINITIONS
# =========================================================

QUESTIONS = [
    {
        "field": "product_name",
        "question": "What is the name of your product?",
    },
    {
        "field": "ingredients",
        "question": "What are the main ingredients in the product?",
    },
    {
        "field": "purpose",
        "question": "What is the purpose or intended use of the product?",
    },
    {
        "field": "product_type",
        "question": "What type of product is it? For example: cosmetic, food, medicine, textile, etc.",
    },
    {
        "field": "jurisdiction",
        "question": "Which country or jurisdiction is the product associated with?",
    },
    {
        "field": "based_on_traditional_knowledge",
        "question": "Is the product based on traditional knowledge? Please answer yes or no.",
    },
]


# =========================================================
# IN-MEMORY SESSION STORAGE
# =========================================================

SESSIONS: Dict[str, Dict[str, Any]] = {}


# =========================================================
# CREATE SESSION
# =========================================================

def create_session() -> Dict[str, Any]:
    """
    Create a new conversation session.
    """

    session_id = str(uuid.uuid4())

    SESSIONS[session_id] = {
        "session_id": session_id,
        "current_question": 0,
        "answers": {},
        "completed": False,
    }

    return SESSIONS[session_id]


# =========================================================
# GET SESSION
# =========================================================

def get_session(
    session_id: str
) -> Dict[str, Any]:

    if session_id not in SESSIONS:

        raise KeyError(
            f"Session not found: {session_id}"
        )

    return SESSIONS[session_id]


# =========================================================
# NEXT QUESTION
# =========================================================

def next_question(
    session_id: str
) -> Dict[str, Any]:
    """
    Return the current question.

    If all questions are answered,
    return completed=True.
    """

    session = get_session(
        session_id
    )

    current_index = session[
        "current_question"
    ]

    # -----------------------------------------------------
    # COMPLETED
    # -----------------------------------------------------

    if current_index >= len(QUESTIONS):

        session["completed"] = True

        return {
            "completed": True,
            "question": None,
            "field": None,
            "question_number": len(QUESTIONS),
            "total_questions": len(QUESTIONS),
            "answers": session["answers"],
        }

    # -----------------------------------------------------
    # CURRENT QUESTION
    # -----------------------------------------------------

    question_data = QUESTIONS[
        current_index
    ]

    return {
        "completed": False,
        "question": question_data["question"],
        "field": question_data["field"],
        "question_number": current_index + 1,
        "total_questions": len(QUESTIONS),
    }


# =========================================================
# SUBMIT ANSWER
# =========================================================

def submit_answer(
    session_id: str,
    answer: str,
) -> Dict[str, Any]:
    """
    Save the current answer and move to the next question.
    """

    session = get_session(
        session_id
    )

    # -----------------------------------------------------
    # CLEAN ANSWER
    # -----------------------------------------------------

    answer = str(
        answer or ""
    ).strip()

    if not answer:

        raise ValueError(
            "Answer cannot be empty."
        )

    # -----------------------------------------------------
    # CHECK COMPLETION
    # -----------------------------------------------------

    if session["current_question"] >= len(QUESTIONS):

        session["completed"] = True

        return {
            "completed": True,
            "message": "All questions have already been answered.",
            "answers": session["answers"],
        }

    # -----------------------------------------------------
    # CURRENT FIELD
    # -----------------------------------------------------

    current_index = session[
        "current_question"
    ]

    current_question = QUESTIONS[
        current_index
    ]

    field = current_question[
        "field"
    ]

    # -----------------------------------------------------
    # SAVE ANSWER
    # -----------------------------------------------------

    # Ingredients can later be converted into a list.
    # For now we preserve exactly what the user entered.
    session["answers"][
        field
    ] = answer

    # -----------------------------------------------------
    # MOVE FORWARD
    # -----------------------------------------------------

    session[
        "current_question"
    ] += 1

    # -----------------------------------------------------
    # CHECK WHETHER COMPLETE
    # -----------------------------------------------------

    if session["current_question"] >= len(QUESTIONS):

        session["completed"] = True

        return {
            "completed": True,
            "message": "All questions completed.",
            "answers": session["answers"],
            "next_question": None,
        }

    # -----------------------------------------------------
    # RETURN NEXT QUESTION
    # -----------------------------------------------------

    next_data = next_question(
        session_id
    )

    return {
        "completed": False,
        "saved_field": field,
        "saved_answer": answer,
        "next_question": next_data,
        "answers": session["answers"],
    }


# =========================================================
# GET ANSWERS
# =========================================================

def get_answers(
    session_id: str
) -> Dict[str, Any]:
    """
    Return all answers collected so far.
    """

    session = get_session(
        session_id
    )

    return dict(
        session["answers"]
    )


# =========================================================
# DELETE SESSION
# =========================================================

def delete_session(
    session_id: str
) -> bool:
    """
    Delete a conversation session.
    """

    if session_id not in SESSIONS:

        return False

    del SESSIONS[
        session_id
    ]

    return True


# =========================================================
# LOCAL TEST
# =========================================================

if __name__ == "__main__":

    print("=" * 60)
    print("IP-SAKTI CONVERSATION TEST")
    print("=" * 60)

    session = create_session()

    session_id = session[
        "session_id"
    ]

    print(
        "Session:",
        session_id
    )

    print()

    # Simulate the conversation
    test_answers = [
        "Ayurvedic Turmeric Aloe Skin Cream",
        "turmeric, aloe vera",
        "Traditional herbal skin care",
        "cosmetic",
        "India",
        "yes",
    ]

    for answer in test_answers:

        question = next_question(
            session_id
        )

        print(
            f"Q{question['question_number']}: "
            f"{question['question']}"
        )

        result = submit_answer(
            session_id,
            answer
        )

        print(
            "Answer:",
            answer
        )

        if result["completed"]:

            print()
            print(
                "Conversation completed."
            )

            print(
                "Collected answers:"
            )

            print(
                result["answers"]
            )

            break

        print(
            "Next:",
            result["next_question"]["question"]
        )

        print()

    print("=" * 60)