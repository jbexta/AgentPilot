from typing import Callable, List, TypeVar

from agentpilot.toolkits.gpt_engineer.ai import AI
from agentpilot.toolkits.gpt_engineer.db import DBs

Step = TypeVar("Step", bound=Callable[[AI, DBs], List[dict]])
