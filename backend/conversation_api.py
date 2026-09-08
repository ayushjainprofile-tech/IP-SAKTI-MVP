"""
IP-SAKTI Conversation API

Provides one-by-one question flow for the IP-SAKTI MVP.

Flow:

    Streamlit
        ↓
    conversation_api.py
        ↓
    conversation.py
        ↓
    Collect product information
        ↓
    main.py /api/analyze
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from conversation import (
    create_session,
    next_question,
    submit_answer,
)


# =========================================================
# ROUTER
# =========================================================

router = APIRouter(
    prefix="/api/conversation",
    tags=["Conversation"],
)


# =========================================================
# REQUEST MODELS
# =========================================================

class StartConversationRequest(BaseModel):
    """
    Empty request body for starting a conversation.

    Streamlit sends:
        {}
    """

    pass


class AnswerRequest(BaseModel):
    """
    Submit the answer to the current question.
    """

    session_id: str
    answer: str


class SessionRequest(BaseModel):
    """
    Request containing an existing session ID.
    """

    session_id: str


# =========================================================
# RESPONSE MODEL
# =========================================================

class StartConversationResponse(BaseModel):

    session_id: str

    completed: bool

    question: Optional[str] = None

    field: Optional[str] = None

    question_number: Optional[int] = None

    total_questions: int


# =========================================================
# START CONVERSATION
# =========================================================

@router.post(
    "/start",
    response_model=StartConversationResponse,
)
def start_conversation(
    request: StartConversationRequest,
):
    """
    Create a new conversation session.

    Returns the first question immediately.
    """

    try:

        # -------------------------------------------------
        # CREATE SESSION
        # -------------------------------------------------

        session = create_session()

        if not isinstance(session, dict):

            raise RuntimeError(
                "conversation.create_session() "
                "did not return a dictionary."
            )

        session_id = session.get(
            "session_id"
        )

        if not session_id:

            raise RuntimeError(
                "Conversation session ID was not created."
            )

        # -------------------------------------------------
        # GET FIRST QUESTION
        # -------------------------------------------------

        question_data = next_question(
            session_id
        )

        if not isinstance(
            question_data,
            dict
        ):

            raise RuntimeError(
                "conversation.next_question() "
                "did not return a dictionary."
            )

        # -------------------------------------------------
        # RESPONSE
        # -------------------------------------------------

        return {
            "session_id": session_id,

            "completed":
                question_data.get(
                    "completed",
                    False
                ),

            "question":
                question_data.get(
                    "question"
                ),

            "field":
                question_data.get(
                    "field"
                ),

            "question_number":
                question_data.get(
                    "question_number"
                ),

            "total_questions":
                question_data.get(
                    "total_questions",
                    0
                ),
        }

    except Exception as e:

        raise HTTPException(
            status_code=500,
            detail=(
                "Could not start conversation: "
                f"{str(e)}"
            ),
        )


# =========================================================
# SUBMIT ANSWER
# =========================================================

@router.post("/answer")
def answer_question(
    request: AnswerRequest,
):
    """
    Submit the answer to the current question.

    The conversation engine saves the answer
    and returns the next question automatically.
    """

    session_id = request.session_id.strip()
    answer = request.answer.strip()

    # -----------------------------------------------------
    # VALIDATE SESSION
    # -----------------------------------------------------

    if not session_id:

        raise HTTPException(
            status_code=400,
            detail="session_id is required.",
        )

    # -----------------------------------------------------
    # VALIDATE ANSWER
    # -----------------------------------------------------

    if not answer:

        raise HTTPException(
            status_code=400,
            detail="Answer cannot be empty.",
        )

    try:

        # -------------------------------------------------
        # SUBMIT TO CONVERSATION ENGINE
        # -------------------------------------------------

        result = submit_answer(
            session_id,
            answer,
        )

        if not isinstance(
            result,
            dict
        ):

            raise RuntimeError(
                "conversation.submit_answer() "
                "did not return a dictionary."
            )

        # -------------------------------------------------
        # RETURN RESULT
        # -------------------------------------------------

        return {
            "success": True,
            **result,
        }

    except KeyError:

        raise HTTPException(
            status_code=404,
            detail="Conversation session not found.",
        )

    except ValueError as e:

        raise HTTPException(
            status_code=400,
            detail=str(e),
        )

    except Exception as e:

        raise HTTPException(
            status_code=500,
            detail=(
                "Could not process answer: "
                f"{str(e)}"
            ),
        )


# =========================================================
# GET CURRENT QUESTION
# =========================================================

@router.post("/question")
def get_current_question(
    request: SessionRequest,
):
    """
    Return the current question for an existing session.
    """

    session_id = request.session_id.strip()

    if not session_id:

        raise HTTPException(
            status_code=400,
            detail="session_id is required.",
        )

    try:

        result = next_question(
            session_id
        )

        if not isinstance(
            result,
            dict
        ):

            raise RuntimeError(
                "conversation.next_question() "
                "did not return a dictionary."
            )

        return {
            "success": True,
            **result,
        }

    except KeyError:

        raise HTTPException(
            status_code=404,
            detail="Conversation session not found.",
        )

    except Exception as e:

        raise HTTPException(
            status_code=500,
            detail=(
                "Could not retrieve question: "
                f"{str(e)}"
            ),
        )


# =========================================================
# GET NEXT QUESTION
# =========================================================

@router.get("/{session_id}/next")
def get_next_question(
    session_id: str,
):
    """
    Get the current/next question using the
    session ID directly in the URL.
    """

    session_id = session_id.strip()

    if not session_id:

        raise HTTPException(
            status_code=400,
            detail="session_id is required.",
        )

    try:

        result = next_question(
            session_id
        )

        if not isinstance(
            result,
            dict
        ):

            raise RuntimeError(
                "conversation.next_question() "
                "did not return a dictionary."
            )

        return {
            "success": True,
            **result,
        }

    except KeyError:

        raise HTTPException(
            status_code=404,
            detail="Conversation session not found.",
        )

    except Exception as e:

        raise HTTPException(
            status_code=500,
            detail=(
                "Could not retrieve next question: "
                f"{str(e)}"
            ),
        )