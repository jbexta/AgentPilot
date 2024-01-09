import time

import openai
from openai import OpenAI
from agentpilot.agent.base import Agent


class CrewAI_Agent:  # (Agent):  # toggle this to enable the plugin
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
                'width': 350,
            },
            {
                'text': 'Goal',
                'type': str,
                'default': '',
                'width': 350,
            },
            {
                'text': 'Backstory',
                'type': str,
                'default': '',
                'width': 350,
                'num_lines': 2,
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
