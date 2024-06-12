from src.gui.config import ConfigFields
from src.members.agent import AgentSettings, Agent
# from interpreter.core.core import OpenInterpreter
# from src.plugins.openinterpreter.src.core.core import OpenInterpreter
# from interpreter import OpenInterpreter
from src.plugins.openinterpreter.src import OpenInterpreter
from src.utils.helpers import split_lang_and_code


class Open_Interpreter(Agent):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.agent_object = None

    def load_agent(self):
        super().load_agent()
        param_dict = {
            'offline': self.config.get('plugin.offline', False),
            'safe_mode': self.config.get('plugin.safe_mode', False),
            'disable_telemetry': self.config.get('plugin.disable_telemetry', False),
            'force_task_completion': self.config.get('plugin.force_task_completion', False),
            'os': self.config.get('plugin.os', True),
        }
        # param_dict['import_skills'] = False  # makes it faster
        self.agent_object = OpenInterpreter(**param_dict)  # None  # todo
        # param_dict = {param['map_to']: self.config.get(f'plugin.{param["text"]}', param['default'])
        #               for param in self.schema
        #               if 'map_to' in param}
        # param_dict = {
        #     'offline': self.config.get('plugin.offline', False),
        #     'safe_mode': self.config.get('plugin.safe_mode', False),
        #     'disable_telemetry': self.config.get('plugin.disable_telemetry', False),
        #     'force_task_completion': self.config.get('plugin.force_task_completion', False),
        #     'os': self.config.get('plugin.os', True),
        # }
        # # param_dict['import_skills'] = False  # makes it faster
        # self.agent_object = OpenInterpreter(**param_dict)  # None  # todo
        # self.agent_object.system_message = self.config.get('context.sys_mgs', '')

    def stream(self, *args, **kwargs):
        base_messages = self.workflow.message_history.get(llm_format=True, calling_member_id=self.member_id)
        # last_user_msg = messages[-1]
        # last_user_msg['type'] = 'message'

        messages = self.convert_messages(base_messages)
        try:
            code_lang = None
            for chunk in self.agent_object.chat(message=messages, display=False, stream=True):
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

    def convert_messages(self, messages):
        new_messages = []
        for message in messages:
            if message['role'] == 'code':
                lang, code = split_lang_and_code(message['content'])
                message['type'] = 'code'
                message['role'] = 'assistant'
                message['format'] = lang
                message['content'] = code

            elif message['role'] == 'output':
                message['type'] = 'console'
                message['role'] = 'computer'
                message['format'] = 'output'
                # message['content'] = message['content']
            else:
                message['type'] = 'message'
            new_messages.append(message)

        return new_messages


class OpenInterpreterSettings(AgentSettings):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.pages.pop('Files')
        self.pages['Chat'].pages['Messages'].schema = [
            {
                'text': 'Model',
                'type': 'ModelComboBox',
                'default': 'gpt-3.5-turbo',
                'row_key': 0,
            },
            {
                'text': 'Display markdown',
                'type': bool,
                'default': True,
                'row_key': 0,
            },
            {
                'text': 'Custom Instructions',
                'key': 'sys_msg',
                'type': str,
                'num_lines': 8,
                'default': '',
                'width': 520,
                'label_position': 'top',
            },
            {
                'text': 'Max messages',
                'type': int,
                'minimum': 1,
                'maximum': 99,
                'default': 10,
                'width': 60,
                'has_toggle': True,
                'row_key': 1,
            },
            {
                'text': 'Max turns',
                'type': int,
                'minimum': 1,
                'maximum': 99,
                'default': 7,
                'width': 60,
                'has_toggle': True,
                'row_key': 1,
            },
            {
                'text': 'Consecutive responses',
                'key': 'on_consecutive_response',
                'type': ('PAD', 'REPLACE', 'NOTHING'),
                'default': 'REPLACE',
                'width': 90,
                'row_key': 2,
            },
            {
                'text': 'User message',
                'key': 'user_msg',
                'type': str,
                'num_lines': 2,
                'default': '',
                'width': 520,
                'label_position': 'top',
                'tooltip': 'Text to override the user/input message. When empty, the default user/input message is used.',
            },
        ]
        info_widget = self.pages['Info']
        info_widget.widgets.append(self.Plugin_Fields(parent=info_widget))

    class Plugin_Fields(ConfigFields):
        def __init__(self, parent):
            super().__init__(parent=parent)
            self.parent = parent
            self.namespace = 'plugin'
            self.schema = [
                {
                    'text': 'Offline',
                    'type': bool,
                    'label_width': 150,
                    'default': False,
                    'map_to': 'offline',
                    # 'width': 190,  # hack to align to centre todo
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
                    'text': 'Disable telemetry',
                    'type': bool,
                    'label_width': 150,
                    'default': False,
                    'map_to': 'disable_telemetry',
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
            # self.config = {}  # reset config on init to

        def get_config(self):
            conf = super().get_config()
            return conf