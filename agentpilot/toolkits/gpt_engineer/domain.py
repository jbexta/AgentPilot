from typing import Callable, List, TypeVar

from toolkits.gpt_engineer.ai import AI
from toolkits.gpt_engineer.db import DBs

Step = TypeVar("Step", bound=Callable[[AI, DBs], List[dict]])
