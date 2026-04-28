from operator import add
from typing import Annotated, Literal, TypedDict

from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import HumanMessage


class QAEntry(TypedDict):
    question: str
    answer: str
    verdict: Literal["correct", "partial", "incorrect"]
    score: int
    feedback: str


class ExaminerState(AgentState):
    topic_name: str
    topic_details: str
    difficulty: Literal["easy", "medium", "hard"]
    candidate_name: str
    num_questions: int
    qa_history: Annotated[list[QAEntry], add]


DEFAULT_NUM_QUESTIONS = 10


class ExaminerStateMiddleware(AgentMiddleware):
    """Extends the deep agent's state with examiner-specific fields."""

    state_schema = ExaminerState

    def before_agent(self, state, runtime):
        if not state.get("messages"):
            n = state.get("num_questions") or DEFAULT_NUM_QUESTIONS
            content = (
                "Begin the exam. The fields from graph state are:\n\n"
                f"- candidate_name: {state.get('candidate_name', '')}\n"
                f"- topic_name: {state.get('topic_name', '')}\n"
                f"- difficulty: {state.get('difficulty', '')}\n"
                f"- num_questions: {n}\n"
                f"- topic_details:\n{state.get('topic_details', '')}"
            )
            return {
                "messages": [HumanMessage(content=content)],
                "num_questions": n,
            }
        return None
