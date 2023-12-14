from agentpilot.agent.base import Agent
from agentpilot.plugins.openinterpreter.src.core.core import Interpreter


class OpenInterpreterAgent(Agent):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.external_params = {
            'system_message': str,
            'messages': list,
            'local': bool,
            'vision': bool,
            'max_output': int,
            'safe_mode': bool,
            'disable_procedures': bool,
            'force_task_completion': bool,
            'max_tokens': int,
            'max_budget': float,
            'os': bool,
        }
        self.agent_object = Interpreter(base_agent=self)
        self.stream_object_base = self.agent_object._streaming_chat
        self.stream_object = None

    def stream(self, *args, **kwargs):
        self.stream_object = self.stream_object_base(self)

        try:
            yield from self.stream_object
        except StopIteration as e:
            return e.value
