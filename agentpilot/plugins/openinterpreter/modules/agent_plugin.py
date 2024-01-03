from agentpilot.agent.base import Agent
from agentpilot.plugins.openinterpreter.src.core.core import Interpreter


class Open_Interpreter(Agent):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.agent_object = Interpreter(base_agent=self)
        self.stream_object_base = self.agent_object._streaming_chat
        self.stream_object = None

        self.extra_params = [
            {
                'text': 'Local',
                'type': bool,
                'default': False,
            },
            {
                'text': 'Vision',
                'type': bool,
                'default': False,
            },
            {
                'text': 'Safe mode',
                'type': bool,
                'default': False,
            },
            {
                'text': 'Disable procedures',
                'type': bool,
                'default': True,
            },
            {
                'text': 'Force task completion',
                'type': bool,
                'default': False,
            },
            {
                'text': 'Max budget',
                'type': float,
                'default': 0.40,
            },
            {
                'text': 'OS',
                'type': bool,
                'default': True,
            },
        ]

        self.param_map = {
            'local': 'local',
            'vision': 'vision',
            'safe_mode': 'safe_mode',
            'disable_procedures': 'disable_procedures',
            'force_task_completion': 'force_task_completion',
            'max_budget': 'max_budget',
            'os': 'os',
        }

    # 'CONFIRM', (language, code)
    # 'PAUSE', None
    # 'assistant', text
    def stream(self, *args, **kwargs):
        self.stream_object = self.stream_object_base(self)

        try:
            for chunk in self.stream_object:
                if isinstance(chunk, tuple):
                    yield chunk
                    continue
                if chunk.get('start', False):
                    continue
                if chunk['type'] == 'message':
                    yield 'assistant', chunk.get('content', '')
                # yield chunk
            # yield from self.stream_object
        except StopIteration as e:
            return e.value
