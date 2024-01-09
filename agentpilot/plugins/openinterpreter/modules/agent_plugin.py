from agentpilot.agent.base import Agent
from agentpilot.plugins.openinterpreter.src.core.core import OpenInterpreter


class Open_Interpreter(Agent):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.agent_object = OpenInterpreter()
        # self.stream_object_base = self.agent_object._streaming_chat
        # self.stream_object = None

        self.extra_params = [
            {
                'text': 'Offline',
                'type': bool,
                'default': False,
                'map_to': 'offline',
            },
            {
                'text': 'Safe mode',
                'type': ('off', 'ask', 'auto',),
                'default': False,
                'map_to': 'safe_mode',
            },
            {
                'text': 'Anonymous telemetry',
                'type': bool,
                'default': True,
                'map_to': 'anonymous_telemetry',
            },
            {
                'text': 'Force task completion',
                'type': bool,
                'default': False,
                'map_to': 'force_task_completion',
            },
            {
                'text': 'OS',
                'type': bool,
                'default': True,
                'map_to': 'os',
            },
        ]

    def load_agent(self):
        super().load_agent()

        for param in self.extra_params:
            if 'map_to' in param:
                setattr(self.agent_object, param['map_to'], self.config.get(f'plugin.{param["text"]}', param['default']))

        self.agent_object.system_message = self.config.get('context.sys_mgs', '')

    # 'CONFIRM', (language, code)
    # 'PAUSE', None
    # 'assistant', text
    def stream(self, *args, **kwargs):
        messages = self.context.message_history.get(llm_format=True, calling_member_id=self.member_id)
        last_user_msg = messages[-1]
        last_user_msg['type'] = 'message'

        try:
            for chunk in self.agent_object._streaming_chat(message=last_user_msg, display=False):
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
