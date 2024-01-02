import time

import openai
from openai import OpenAI
from agentpilot.agent.base import Agent


class CrewAI_Agent(Agent):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.extra_params = [
            {
                'text': 'Executor',
                'type': ('Sequential',),
                'default': 'Sequential',
            },
            {
                'text': 'Role',
                'type': str,
                'default': '',
            },
            {
                'text': 'Goal',
                'type': str,
                'default': '',
            },
            {
                'text': 'Backstory',
                'type': str,
                'default': '',
                'width': 250,
            },
            {
                'text': 'Memory',
                'type': bool,
                'default': True,
            },
            {
                'text': 'Allow delegation',
                'type': bool,
                'default': True,
            },
        ]

    def load_agent(self):
        # We need to link to an orchestrator agent here if there is one, to get the appropriate stream object
        pass

    def stream(self, *args, **kwargs):
        pass
