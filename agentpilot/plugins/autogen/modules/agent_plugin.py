import time

import openai
from openai import OpenAI
from agentpilot.agent.base import Agent


class Autogen(Agent):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.external_params = {
            'agent_type': [
                ''
            ],
            'code_interpreter': bool,
        }

    def stream(self, *args, **kwargs):
        pass
