
from src.agent.base import Agent
from interpreter.core.core import OpenInterpreter


class Open_Interpreter(Agent):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.agent_object = OpenInterpreter()

        self.schema = [
            {
                'text': 'Offline',
                'type': bool,
                'label_width': 150,
                'default': False,
                'map_to': 'offline',
                'width': 190,  # hack to align to centre todo
            },
            {
                'text': 'Safe mode',
                'type': ('off', 'ask', 'auto',),
                'label_width': 150,
                'default': False,
                'map_to': 'safe_mode',
                'width': 75,
            },
            {
                'text': 'Anonymous telemetry',
                'type': bool,
                'label_width': 150,
                'default': True,
                'map_to': 'anonymous_telemetry',
            },
            {
                'text': 'Force task completion',
                'type': bool,
                'label_width': 150,
                'default': False,
                'map_to': 'force_task_completion',
            },
            {
                'text': 'OS',
                'type': bool,
                'label_width': 150,
                'default': True,
                'map_to': 'os',
            },
        ]

    def load_agent(self):
        super().load_agent()

        for param in self.schema:
            if 'map_to' in param:
                setattr(self.agent_object, param['map_to'], self.config.get(f'plugin.{param["text"]}', param['default']))

        # self.agent_object.system_message = self.config.get('context.sys_mgs', '')

    def stream(self, *args, **kwargs):
        messages = self.workflow.message_history.get(llm_format=True, calling_member_id=self.member_id)
        last_user_msg = messages[-1]
        last_user_msg['type'] = 'message'

        try:
            code_lang = None
            for chunk in self.agent_object._streaming_chat(message=last_user_msg, display=False):
                if chunk.get('start', False) or chunk.get('end', False):
                    continue

                if chunk['type'] == 'message':
                    yield 'assistant', chunk.get('content', '')

                elif chunk['type'] == 'code':
                    if code_lang is None:
                        code_lang = chunk['format']
                        yield 'code', f'```{code_lang}\n'

                    code = chunk['content']
                    yield 'code', code
                elif chunk['type'] == 'confirmation':
                    yield 'code', '\n```'
                    break
                else:
                    print('Unknown chunk type:', chunk['type'])
                    # raise ValueError(f'Unknown chunk type: {chunk["type"]}')

        except StopIteration as e:
            return e.value
