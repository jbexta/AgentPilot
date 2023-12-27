import time

import openai
from openai import OpenAI
from agentpilot.agent.base import Agent


class Autogen(Agent):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.extra_params = {
            ('agent_type', ('ConversableAgent','AssistantAgent',), 'ConversableAgent'),
            ('code_interpreter', bool, True),
        }

    def load_agent(self):
        # We need to link to an orchestrator agent here if there is one, to get the appropriate stream object
        pass

    def stream(self, *args, **kwargs):
        pass
