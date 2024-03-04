import time

import openai
from openai import OpenAI
from agentpilot.agent.base import Agent


class Autogen:  # (Agent):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.group_key = 'autogen'  # Must match the directory name of the context plugin
        # If all agents in a group have the same key, the corresponding context plugin will be used
        self.schema = [
            {
                'text': 'agent_type',
                'type': ('ConversableAgent','AssistantAgent',),
                'default': 'ConversableAgent',
            },
        ]

    # def load_agent(self):
    #
    #     # We need to link to an orchestrator agent here if there is one, to get the appropriate stream object
    #     pass

    # def stream(self, *args, **kwargs):
    #     pass
