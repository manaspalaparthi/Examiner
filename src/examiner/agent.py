from deepagents import create_deep_agent

from .model import get_model
from .prompts import EXAMINER_INSTRUCTIONS
from .state import ExaminerStateMiddleware
from .tools import ask_candidate, record_evaluation

agent = create_deep_agent(
    model=get_model(),
    tools=[ask_candidate, record_evaluation],
    system_prompt=EXAMINER_INSTRUCTIONS,
    middleware=[ExaminerStateMiddleware()],
).with_config({"recursion_limit": 100})
