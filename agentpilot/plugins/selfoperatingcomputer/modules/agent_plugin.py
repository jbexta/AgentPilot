from agentpilot.agent.base import Agent
from agentpilot.plugins.selfoperatingcomputer.src import main


class SelfOperatingComputerAgent(Agent):
    def __init__(self, base_agent):
        super().__init__()
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
        self.base_agent = base_agent
        self.agent_object = Interpreter()
        self.stream_object_base = self.agent_object.get_chat_stream
        self.stream_object = None

    def stream(self):
        self.stream_object = self.stream_object_base(self.base_agent)

        try:
            yield from self.stream_object
        except StopIteration as e:
            return e.value
