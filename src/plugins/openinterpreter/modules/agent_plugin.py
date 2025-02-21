from PySide6.QtGui import Qt
from PySide6.QtWidgets import QVBoxLayout

from src.gui.config import ConfigFields, ConfigTabs, ConfigJoined, ConfigJsonTree
from src.members.agent import AgentSettings, Agent
# from src.plugins.openinterpreter.src import OpenInterpreter
# from interpreter.core.core import OpenInterpreter
# from plugins.openinterpreter.src.core.core import OpenInterpreter
# from interpreter import OpenInterpreter
from src.plugins.openinterpreter.src import OpenInterpreter
from src.utils.helpers import split_lang_and_code, convert_model_json_to_obj


class Open_Interpreter(Agent):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.agent_object = None

    def load(self):
        super().load()
        param_dict = {
            'offline': self.config.get('plugin.offline', False),
            'max_output': self.config.get('code.max_output', 2800),
            'safe_mode': self.config.get('plugin.safe_mode', 'off'),
            'loop': self.config.get('loop.loop', False),
            'loop_message': self.config.get('loop.loop_message', """Proceed. You CAN run code on my machine. If you want to run code, start your message with "```"! If the entire task I asked for is done, say exactly 'The task is done.' If you need some specific information (like username or password) say EXACTLY 'Please provide more information.' If it's impossible, say 'The task is impossible.' (If I haven't provided a task, say exactly 'Let me know what you'd like to do next.') Otherwise keep going."""),
            'disable_telemetry': self.config.get('plugin.disable_telemetry', False),
            'os': self.config.get('plugin.os', True),
            # 'system_message': self.system_message(),
            'custom_instructions': self.config.get('chat.custom_instructions', ''),
            'user_message_template': self.config.get('chat.user_message_template', '{content}'),
            'code_output_template': self.config.get('code.code_output_template', "Code output: {content}\n\nWhat does this output mean / what's next (if anything, or are we done)?"),
            'empty_code_output_template': self.config.get('code.empty_code_output_template', "The code above was executed on my machine. It produced no text output. what's next (if anything, or are we done?)"),
            'code_output_sender': self.config.get('code.code_output_sender', 'user'),
            'import_skills': False,
        }
        self.agent_object = OpenInterpreter(**param_dict)
        # print('## Loaded OpenInterpreter obj')

        # model_name = self.config.get('chat.model', 'gpt-4-turbo')

        model_json = self.config.get('chat.model')
        model_obj = convert_model_json_to_obj(model_json)
        model_name = model_obj['model_name']

        model_params = self.main.system.providers.get_model_parameters(model_obj)
        # print('## Fetched model params')
        self.agent_object.llm.model = model_name
        self.agent_object.llm.temperature = model_params.get('temperature', 0)
        self.agent_object.llm.max_tokens = model_params.get('max_tokens', None)
        self.agent_object.llm.api_key = model_params.get('api_key', None)
        self.agent_object.llm.api_base = model_params.get('api_base', None)

    async def stream(self, *args, **kwargs):
        self.agent_object.system_message = self.system_message()  # put this here to only compute blocks when needed
        native_messages = self.workflow.message_history.get_llm_messages(calling_member_id=self.member_id)
        messages = self.convert_messages(native_messages)
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

        except StopIteration as e:
            raise NotImplementedError('StopIteration')

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
            else:
                message['type'] = 'message'
            new_messages.append(message)

        return new_messages


class OpenInterpreterSettings(AgentSettings):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # self.pages.pop('Files')
        self.pages.pop('Tools')
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
                'text': 'System message',
                'key': 'sys_msg',
                'type': str,
                'num_lines': 2,
                'default': '',
                'stretch_x': True,
                'stretch_y': True,
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
                'text': 'Custom instructions',
                'type': str,
                'num_lines': 2,
                'default': '',
                'stretch_x': True,
                'label_position': 'top',
                'row_key': 2,
            },
            {
                'text': 'User message template',
                'type': str,
                'num_lines': 2,
                'default': '{content}',
                'stretch_x': True,
                'label_position': 'top',
                'row_key': 2,
            },
        ]
        info_widget = self.pages['Info']
        info_widget.widgets.append(self.Plugin_Fields(parent=info_widget))

        self.pages['Loop'] = self.Loop_Settings(parent=self.pages['Chat'])
        self.pages['Code'] = self.Code_Settings(parent=self.pages['Chat'])

    class Plugin_Fields(ConfigFields):
        def __init__(self, parent):
            super().__init__(parent=parent)
            self.parent = parent
            self.conf_namespace = 'plugin'
            self.label_width = 150
            self.schema = [
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
                    'width': 75,
                },
                {
                    'text': 'Disable telemetry',
                    'type': bool,
                    'default': False,
                    'map_to': 'disable_telemetry',
                },
                {
                    'text': 'OS',
                    'type': bool,
                    'default': True,
                    'map_to': 'os',
                },
            ]

    class Loop_Settings(ConfigJoined):
        def __init__(self, parent):
            super().__init__(parent=parent, layout_type='vertical')
            self.widgets = [
                self.Loop_Fields(parent=self),
                # self.Info_Plugin(parent=self),
            ]

        class Loop_Fields(ConfigFields):
            def __init__(self, parent):
                super().__init__(parent=parent)
                self.parent = parent
                self.conf_namespace = 'loop'
                self.field_alignment = Qt.AlignHCenter
                self.schema = [
                    {
                        'text': 'Loop',
                        'type': bool,
                        # 'label_width': 150,
                        'default': False,
                    },
                    {
                        'text': 'Loop message',
                        'type': str,
                        # 'label_width': 150,
                        'stretch_x': True,
                        'num_lines': 5,
                        'label_position': 'top',
                        'default': """Proceed. You CAN run code on my machine. If you want to run code, start your message with "```"! If the entire task I asked for is done, say exactly 'The task is done.' If you need some specific information (like username or password) say EXACTLY 'Please provide more information.' If it's impossible, say 'The task is impossible.' (If I haven't provided a task, say exactly 'Let me know what you'd like to do next.') Otherwise keep going.""",
                    }
                ]

        class Loop_Breakers(ConfigJsonTree):
            def __init__(self, parent):
                super().__init__(parent=parent,
                                 add_item_options={'title': 'NA', 'prompt': 'NA'},
                                 del_item_options={'title': 'NA', 'prompt': 'NA'})
                self.parent = parent
                self.conf_namespace = 'loop.breakers'
                self.schema = [
                    {
                        'text': 'Loop breakers',
                        'type': str,
                        'width': 120,
                        'default': 'Variable name',
                    },
                    {
                        'text': 'Value',
                        'type': str,
                        'stretch': True,
                        'default': '',
                    },
                ]

    class Code_Settings(ConfigFields):
        def __init__(self, parent):
            super().__init__(parent=parent)
            self.parent = parent
            self.conf_namespace = 'code'
            self.schema = [
                {
                    'text': 'Code output template',
                    'type': str,
                    'num_lines': 4,
                    'label_position': 'top',
                    'stretch_x': True,
                    'default': "Code output: {content}\n\nWhat does this output mean / what's next (if anything, or are we done)?",
                },
                {
                    'text': 'Empty code output template',
                    'type': str,
                    'num_lines': 4,
                    'label_position': 'top',
                    'stretch_x': True,
                    'default': "The code above was executed on my machine. It produced no text output. what's next (if anything, or are we done?)"
                },
                {
                    'text': 'Code output sender',
                    'type': str,
                    'label_position': 'top',
                    'default': 'user',
                },
                {
                    'text': 'Max output',
                    'type': int,
                    'minimum': 1,
                    'maximum': 69420,
                    'step': 100,
                    'default': 2800,
                }
            ]

# class OpenInterpreterSettings(AgentSettings):
#     def __init__(self, *args, **kwargs):
#         super().__init__(*args, **kwargs)
#         # self.pages.pop('Files')
#         page_widget = self.widgets[1]
#         page_widget.pages.pop('Tools')
#         page_widget.pages['Chat'].pages['Messages'].schema = [
#             {
#                 'text': 'Model',
#                 'type': 'ModelComboBox',
#                 'default': 'gpt-3.5-turbo',
#                 'row_key': 0,
#             },
#             {
#                 'text': 'Display markdown',
#                 'type': bool,
#                 'default': True,
#                 'row_key': 0,
#             },
#             {
#                 'text': 'System message',
#                 'key': 'sys_msg',
#                 'type': str,
#                 'num_lines': 2,
#                 'default': '',
#                 'stretch_x': True,
#                 'stretch_y': True,
#                 'label_position': 'top',
#             },
#             {
#                 'text': 'Max messages',
#                 'type': int,
#                 'minimum': 1,
#                 'maximum': 99,
#                 'default': 10,
#                 'width': 60,
#                 'has_toggle': True,
#                 'row_key': 1,
#             },
#             {
#                 'text': 'Max turns',
#                 'type': int,
#                 'minimum': 1,
#                 'maximum': 99,
#                 'default': 7,
#                 'width': 60,
#                 'has_toggle': True,
#                 'row_key': 1,
#             },
#             {
#                 'text': 'Custom instructions',
#                 'type': str,
#                 'num_lines': 2,
#                 'default': '',
#                 'stretch_x': True,
#                 'label_position': 'top',
#                 'row_key': 2,
#             },
#             {
#                 'text': 'User message template',
#                 'type': str,
#                 'num_lines': 2,
#                 'default': '{content}',
#                 'stretch_x': True,
#                 'label_position': 'top',
#                 'row_key': 2,
#             },
#         ]
#         info_widget = page_widget.pages['Info']
#         info_widget.widgets.append(self.Plugin_Fields(parent=info_widget))
#
#         page_widget.pages['Loop'] = self.Loop_Settings(parent=page_widget.pages['Chat'])
#         page_widget.pages['Code'] = self.Code_Settings(parent=page_widget.pages['Chat'])
#
#     class Plugin_Fields(ConfigFields):
#         def __init__(self, parent):
#             super().__init__(parent=parent)
#             self.parent = parent
#             self.conf_namespace = 'plugin'
#             self.label_width = 150
#             self.schema = [
#                 {
#                     'text': 'Offline',
#                     'type': bool,
#                     'default': False,
#                     'map_to': 'offline',
#                 },
#                 {
#                     'text': 'Safe mode',
#                     'type': ('off', 'ask', 'auto',),
#                     'default': False,
#                     'map_to': 'safe_mode',
#                     'width': 75,
#                 },
#                 {
#                     'text': 'Disable telemetry',
#                     'type': bool,
#                     'default': False,
#                     'map_to': 'disable_telemetry',
#                 },
#                 {
#                     'text': 'OS',
#                     'type': bool,
#                     'default': True,
#                     'map_to': 'os',
#                 },
#             ]
#
#     class Loop_Settings(ConfigJoined):
#         def __init__(self, parent):
#             super().__init__(parent=parent, layout_type=QVBoxLayout)
#             self.widgets = [
#                 self.Loop_Fields(parent=self),
#                 # self.Info_Plugin(parent=self),
#             ]
#
#         class Loop_Fields(ConfigFields):
#             def __init__(self, parent):
#                 super().__init__(parent=parent)
#                 self.parent = parent
#                 self.conf_namespace = 'loop'
#                 self.field_alignment = Qt.AlignHCenter
#                 self.schema = [
#                     {
#                         'text': 'Loop',
#                         'type': bool,
#                         # 'label_width': 150,
#                         'default': False,
#                     },
#                     {
#                         'text': 'Loop message',
#                         'type': str,
#                         # 'label_width': 150,
#                         'stretch_x': True,
#                         'num_lines': 5,
#                         'label_position': 'top',
#                         'default': """Proceed. You CAN run code on my machine. If you want to run code, start your message with "```"! If the entire task I asked for is done, say exactly 'The task is done.' If you need some specific information (like username or password) say EXACTLY 'Please provide more information.' If it's impossible, say 'The task is impossible.' (If I haven't provided a task, say exactly 'Let me know what you'd like to do next.') Otherwise keep going.""",
#                     }
#                 ]
#
#         class Loop_Breakers(ConfigJsonTree):
#             def __init__(self, parent):
#                 super().__init__(parent=parent,
#                                  add_item_options={'title': 'NA', 'prompt': 'NA'},
#                                  del_item_options={'title': 'NA', 'prompt': 'NA'})
#                 self.parent = parent
#                 self.conf_namespace = 'loop.breakers'
#                 self.schema = [
#                     {
#                         'text': 'Loop breakers',
#                         'type': str,
#                         'width': 120,
#                         'default': 'Variable name',
#                     },
#                     {
#                         'text': 'Value',
#                         'type': str,
#                         'stretch': True,
#                         'default': '',
#                     },
#                 ]
#
#     class Code_Settings(ConfigFields):
#         def __init__(self, parent):
#             super().__init__(parent=parent)
#             self.parent = parent
#             self.conf_namespace = 'code'
#             self.schema = [
#                 {
#                     'text': 'Code output template',
#                     'type': str,
#                     'num_lines': 4,
#                     'label_position': 'top',
#                     'stretch_x': True,
#                     'default': "Code output: {content}\n\nWhat does this output mean / what's next (if anything, or are we done)?",
#                 },
#                 {
#                     'text': 'Empty code output template',
#                     'type': str,
#                     'num_lines': 4,
#                     'label_position': 'top',
#                     'stretch_x': True,
#                     'default': "The code above was executed on my machine. It produced no text output. what's next (if anything, or are we done?)"
#                 },
#                 {
#                     'text': 'Code output sender',
#                     'type': str,
#                     'label_position': 'top',
#                     'default': 'user',
#                 },
#                 {
#                     'text': 'Max output',
#                     'type': int,
#                     'minimum': 1,
#                     'maximum': 69420,
#                     'step': 100,
#                     'default': 2800,
#                 }
#             ]
