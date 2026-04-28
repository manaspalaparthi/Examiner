from typing import Annotated, Literal

from langchain_core.messages import ToolMessage
from langchain_core.tools import InjectedToolCallId, tool
from langgraph.prebuilt import InjectedState
from langgraph.types import Command, interrupt

from .state import ExaminerState


@tool
def ask_candidate(question: str) -> str:
    """Pose a single question to the candidate and wait for their typed answer.

    The graph pauses here via a LangGraph interrupt; the candidate's answer
    is supplied by the caller (Studio UI or `Command(resume=...)` over the
    REST API) and returned as this tool's value.
    """
    answer = interrupt({"type": "question", "question": question})
    return str(answer)


@tool
def record_evaluation(
    question: str,
    answer: str,
    verdict: Literal["correct", "partial", "incorrect"],
    score: int,
    feedback: str,
    state: Annotated[ExaminerState, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """Append one evaluated Q/A pair to qa_history. Score is 0-10."""
    clamped = max(0, min(10, int(score)))
    entry = {
        "question": question,
        "answer": answer,
        "verdict": verdict,
        "score": clamped,
        "feedback": feedback,
    }
    recorded = len(state.get("qa_history", [])) + 1
    total = state.get("num_questions") or 10
    return Command(
        update={
            "qa_history": [entry],
            "messages": [
                ToolMessage(
                    f"Recorded Q{recorded}/{total}: verdict={verdict}, score={clamped}.",
                    tool_call_id=tool_call_id,
                )
            ],
        }
    )
