
from abc import abstractmethod
from PySide6.QtWidgets import *
from PySide6.QtGui import Qt
import json

from src.utils import sql
from src.utils.helpers import convert_model_json_to_obj, convert_to_safe_case

from src.gui.config import ConfigPages, ConfigFields, ConfigTabs, ConfigJsonTree, \
    ConfigJoined, ConfigJsonFileTree, ConfigJsonToolTree, ConfigVoiceTree, CHBoxLayout
from src.gui.widgets import find_main_widget
from src.members.base import Member
from src.utils.messages import CharProcessor


class Agent(Member):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.name = self.config.get('info.name', 'Assistant')

        self.tools_table = {}
        self.tools = {}

        self.load_tools()

    def load(self):
        pass

    def load_tools(self):
        tools_in_config = json.loads(self.config.get('tools.data', '[]'))
        agent_tools_ids = [tool['id'] for tool in tools_in_config]
        if len(agent_tools_ids) == 0:
            return []

        self.tools_table = sql.get_results(f"""
            SELECT
                uuid,
                name,
                config
            FROM tools
            WHERE 
                -- json_extract(config, '$.method') = ? AND
                uuid IN ({','.join(['?'] * len(agent_tools_ids))})
        """, agent_tools_ids)

    def system_message(self, msgs_in_system=None, response_instruction='', msgs_in_system_len=0):
        raw_sys_msg = self.config.get('chat.sys_msg', '')
        members = self.workflow.members
        member_names = {m_id: member.config.get('info.name', 'Assistant') for m_id, member in members.items()}
        member_placeholders = {m_id: member.config.get('group.output_placeholder', f'{member_names[m_id]}_{str(m_id)}')
                               for m_id, member in members.items()}
        member_last_outputs = {member.member_id: member.last_output for k, member in self.workflow.members.items() if member.last_output != ''}
        member_blocks_dict = {member_placeholders[k]: v for k, v in member_last_outputs.items() if v is not None}
        agent_blocks = json.loads(self.config.get('blocks.data', '{}'))
        agent_blocks_dict = {block['placeholder']: block['value'] for block in agent_blocks}

        builtin_blocks = {
            'char_name': self.name,
            'full_name': self.name,
            'response_type': 'response',
            'verb': '',
        }
        formatted_sys_msg = self.workflow.system.blocks.format_string(
            raw_sys_msg,
            additional_blocks={**member_blocks_dict, **agent_blocks_dict, **builtin_blocks}
        )

        message_str = ''
        if msgs_in_system:
            if msgs_in_system_len > 0:
                msgs_in_system = msgs_in_system[-msgs_in_system_len:]
            message_str = "\n".join(
                f"""{msg['role']}: \"{msg['content'].strip().strip('"')}\"""" for msg in msgs_in_system)
            message_str = f"\n\nCONVERSATION:\n\n{message_str}\nassistant: "
        if response_instruction != '':
            response_instruction = f"\n\n{response_instruction}\n\n"

        return formatted_sys_msg + response_instruction + message_str

    async def run_member(self):
        """The entry response method for the member."""
        async for key, chunk in self.receive():
            if self.workflow.stop_requested:
                self.workflow.stop_requested = False
                break

            yield key, chunk
            if self.main:
                self.main.new_sentence_signal.emit(key, self.full_member_id(), chunk)
        # pass

    async def receive(self):
        from src.system.base import manager  # todo
        system_msg = self.system_message()
        messages = self.workflow.message_history.get_llm_messages(calling_member_id=self.full_member_id())  # , bridge_full_member_id=bridge_full_member_id)

        if system_msg != '':
            messages.insert(0, {'role': 'system', 'content': system_msg})

        model_json = self.config.get('chat.model', manager.config.dict.get('system.default_chat_model', 'mistral/mistral-large-latest'))
        model_obj = convert_model_json_to_obj(model_json)

        stream = self.stream(model=model_obj, messages=messages)
        role_responses = {}

        async for key, chunk in stream:
            if key not in role_responses:
                role_responses[key] = ''
            if key == 'tools':
                tool_list = chunk
                role_responses['tools'] = tool_list
            else:
                chunk = chunk or ''
                role_responses[key] += chunk
                yield key, chunk

        if 'api_key' in model_obj['model_params']:
            model_obj['model_params'].pop('api_key')
        logging_obj = {
            'context_id': self.workflow.context_id,
            'member_id': self.full_member_id(),
            'model': model_obj,
            'messages': messages,
            'role_responses': role_responses,
        }

        for key, response in role_responses.items():
            if key == 'tools':
                all_tools = response
                for tool in all_tools:
                    tool_args_json = tool['function']['arguments']
                    # tool_name = tool_name.replace('_', ' ').capitalize()
                    tools = self.main.system.tools.to_dict()
                    first_matching_name = next((k for k, v in tools.items()
                                              if convert_to_safe_case(k) == tool['function']['name']),
                                             None)  # todo add duplicate check, or
                    first_matching_id = sql.get_scalar("SELECT uuid FROM tools WHERE name = ?",
                                                       (first_matching_name,))
                    msg_content = json.dumps({
                        'tool_uuid': first_matching_id,
                        'name': tool['function']['name'],
                        'args': tool_args_json,
                        'text': tool['function']['name'].replace('_', ' ').capitalize(),
                        # 'auto_run': tools[first_matching_name].get('bubble.auto_run', False),
                    })
                    self.workflow.save_message('tool', msg_content, self.full_member_id(), logging_obj)
            else:
                if response != '':
                    self.workflow.save_message(key, response, self.full_member_id(), logging_obj)
                    self.last_output = response
                    self.turn_output = response

    async def stream(self, model, messages):
        from src.system.base import manager
        tools = self.get_function_call_tools()

        # xml_tag_roles = json.loads(self.config.get('prompt_model', '[]'))
        xml_tag_roles = json.loads(model.get('model_params', {}).get('xml_roles.data', '[]'))
        xml_tag_roles = {tag_dict['xml_tag'].lower(): tag_dict['map_to_role'] for tag_dict in xml_tag_roles}
        processor = CharProcessor(tag_roles=xml_tag_roles, default_role='assistant')

        stream = await manager.providers.run_model(
            model_obj=model,
            messages=messages,
            tools=tools
        )
        collected_tools = []

        async for resp in stream:
            delta = resp.choices[0].get('delta', {})
            if not delta:
                continue
            content = delta.get('content', None) or ''
            tool_calls = delta.get('tool_calls', None)
            if tool_calls:
                tool_chunks = delta.tool_calls
                for t_chunk in tool_chunks:
                    if len(collected_tools) <= t_chunk.index:
                        collected_tools.append({"id": "", "type": "function", "function": {"name": "", "arguments": ""}})
                    tc = collected_tools[t_chunk.index]

                    if t_chunk.id:
                        tc["id"] += t_chunk.id
                    if t_chunk.function.name:
                        tc["function"]["name"] += t_chunk.function.name
                    if t_chunk.function.arguments:
                        tc["function"]["arguments"] += t_chunk.function.arguments

            if content != '':
                async for role, content in processor.process_chunk(content):
                    if role != 'assistant':
                        pass
                    yield role, content
        async for role, content in processor.process_chunk(None):
            yield role, content  # todo to get last char

        if len(collected_tools) > 0:
            yield 'tools', collected_tools

    def get_function_call_tools(self):
        formatted_tools = []
        for tool_id, tool_name, tool_config in self.tools_table:
            tool_config = json.loads(tool_config)
            parameters_data = tool_config.get('parameters.data', '[]')
            transformed_parameters = self.transform_parameters(parameters_data)

            formatted_tools.append(
                {
                    'type': 'function',
                    'function': {
                        'name': convert_to_safe_case(tool_name),
                        'description': tool_config.get('description', ''),
                        'parameters': transformed_parameters
                    }
                }
            )

        return formatted_tools

    def transform_parameters(self, parameters_data):
        """Transform the parameter data from the config to LLM format."""
        parameters = json.loads(parameters_data)

        transformed = {
            'type': 'object',
            'properties': {},
            'required': []
        }

        # Iterate through each parameter and convert it
        for parameter in parameters:
            param_name = convert_to_safe_case(parameter['name'])
            param_desc = parameter['description']
            param_type = parameter['type'].lower()
            param_required = parameter['req']
            param_default = parameter['default']

            type_map = {
                'string': 'string',
                'int': 'integer',
                'float': 'number',
                'bool': 'boolean',
            }
            transformed['properties'][param_name] = {
                'type': type_map.get(param_type, 'string'),
                'description': param_desc,
            }
            if param_required:
                transformed['required'].append(param_name)

        return transformed


class StreamSpeaker:
    def __init__(self, member):
        self.member = member
        self.previous_blocks = []  # list of tuple(block_text, audio_file_id)
        self.chunk_chars = ['.', '?', '!', '\n', ': ', ';']  # , ',']
        self.current_block = ''

    def stream_chunk(self, chunk):
        if chunk is None or chunk == '':
            return
        self.current_block += chunk

        if any(c in chunk for c in self.chunk_chars):
            self.push_block()

    def finish_stream(self):
        self.push_block()

    def push_block(self):
        if self.current_block == '':
            return

        self.generate_voices(self.msg_uuid, self.current_block, '')
        self.current_block = ''


class AgentSettings(ConfigPages):
    def __init__(self, parent):
        super().__init__(parent=parent)
        self.main = find_main_widget(parent)
        self.member_type = 'agent'
        self.member_id = None
        self.layout.addSpacing(10)

        self.pages = {
            'Info': self.Info_Settings(self),
            'Chat': self.Chat_Settings(self),
            # 'Files': self.File_Settings(self),
            'Tools': self.Tool_Settings(self),
        }

    @abstractmethod
    def save_config(self):
        """Saves the config to database when modified"""
        pass

    class Info_Settings(ConfigJoined):
        def __init__(self, parent):
            super().__init__(parent=parent, layout_type=QVBoxLayout)
            self.widgets = [
                self.Info_Fields(parent=self),
            ]

        class Info_Fields(ConfigFields):
            def __init__(self, parent):
                super().__init__(parent=parent)
                self.conf_namespace = 'info'
                self.alignment = Qt.AlignHCenter
                self.schema = [
                    {
                        'text': 'Avatar',
                        'key': 'avatar_path',
                        'type': 'CircularImageLabel',
                        'default': '',
                        'label_position': None,
                    },
                    {
                        'text': 'Name',
                        'type': str,
                        'default': 'Assistant',
                        'stretch_x': True,
                        'text_size': 15,
                        'text_alignment': Qt.AlignCenter,
                        'label_position': None,
                        'transparent': True,
                    },
                    {
                        'text': 'Plugin',
                        'key': 'use_plugin',
                        'type': 'PluginComboBox',
                        'label_position': None,
                        'plugin_type': 'Agent',
                        'centered': True,
                        'default': '',
                    }
                ]

    class Chat_Settings(ConfigTabs):
        def __init__(self, parent):
            super().__init__(parent=parent)

            self.pages = {
                'Messages': self.Page_Chat_Messages(parent=self),
                'Preload': self.Page_Chat_Preload(parent=self),
                # 'Output': self.Page_Chat_Output(parent=self),
                'Variables': self.Page_Chat_Variables(parent=self),
                'Group': self.Page_Chat_Group(parent=self),
                # 'Voice': self.Page_Chat_Voice(parent=self),
            }

        class Page_Chat_Messages(ConfigFields):
            def __init__(self, parent):
                super().__init__(parent=parent)
                from src.system.base import manager
                self.conf_namespace = 'chat'
                self.schema = [
                    {
                        'text': 'Model',
                        'type': 'ModelComboBox',
                        'default': '',  # convert_model_json_to_obj(manager.config.dict.get('system.default_chat_model', 'mistral/mistral-large-latest')),  # 'mistral/mistral-large-latest',
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
                        'num_lines': 12,
                        'default': '',
                        'stretch_x': True,
                        'gen_block_folder_id': 4,
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
                ]

        class Page_Chat_Preload(ConfigJsonTree):
            def __init__(self, parent):
                super().__init__(parent=parent,
                                 add_item_prompt=('NA', 'NA'),
                                 del_item_prompt=('NA', 'NA'))
                self.conf_namespace = 'chat.preload'
                self.schema = [
                    {
                        'text': 'Role',
                        'type': 'RoleComboBox',
                        'width': 120,
                        'default': 'assistant',
                    },
                    {
                        'text': 'Content',
                        'type': str,
                        'stretch': True,
                        'wrap_text': True,
                        'default': '',
                    },
                    {
                        'text': 'Type',
                        'type': ('Normal', 'Context', 'Welcome'),
                        'width': 90,
                        'default': 'Normal',
                    },
                ]

        # class Page_Chat_Output(ConfigJsonTree):
        #     def __init__(self, parent):
        #         super().__init__(parent=parent,
        #                          add_item_prompt=('NA', 'NA'),
        #                          del_item_prompt=('NA', 'NA'))
        #         self.conf_namespace = 'chat.output'
        #         self.schema = [
        #             {
        #                 'text': 'XML Tag',
        #                 'type': str,
        #                 'stretch': True,
        #                 'default': '',
        #             },
        #             {
        #                 'text': 'Map to role',
        #                 'type': 'RoleComboBox',
        #                 'width': 120,
        #                 'default': 'assistant',
        #             },
        #         ]

        class Page_Chat_Variables(ConfigJsonTree):
            def __init__(self, parent):
                super().__init__(parent=parent,
                                 add_item_prompt=('NA', 'NA'),
                                 del_item_prompt=('NA', 'NA'))
                self.conf_namespace = 'blocks'
                self.schema = [
                    {
                        'text': 'Placeholder',
                        'type': str,
                        'width': 120,
                        'default': '< Placeholder >',
                    },
                    {
                        'text': 'Value',
                        'type': str,
                        'stretch': True,
                        'wrap_text': True,
                        'default': '',
                    },
                ]

        class Page_Chat_Group(ConfigFields):
            def __init__(self, parent):
                super().__init__(parent=parent)
                self.conf_namespace = 'group'
                self.label_width = 175
                self.schema = [
                    {
                        'text': 'Hide bubbles',
                        'type': bool,
                        'tooltip': 'When checked, the responses from this member will not be shown in the chat',
                        'default': False,
                    },
                    {
                        'text': 'Output placeholder',
                        'type': str,
                        'tooltip': 'A tag to use this member\'s output from other members system messages',
                        'default': '',
                    },
                    {
                        'text': 'On multiple inputs',
                        'type': ('Append to system msg', 'Merged user message', 'Reply individually'),
                        'tooltip': 'How to handle multiple inputs from the user (Not implemented yet)',
                        'default': 'Merged user message',
                    },
                    {
                        'text': 'Show members as user role',
                        'type': bool,
                        'default': True,
                    },
                    {
                        'text': 'Member description',
                        'type': str,
                        'num_lines': 4,
                        # 'label_position': 'top',
                        'stretch_x': True,
                        'tooltip': 'A description of the member that can be used by other members (Not implemented yet)',
                        'default': '',
                    }
                ]

        # class Page_Chat_Voice(ConfigVoiceTree):
        #     def __init__(self, parent):
        #         super().__init__(parent=parent)

    class File_Settings(ConfigJsonFileTree):
        def __init__(self, parent):
            self.IS_DEV_MODE = True
            super().__init__(parent=parent,
                             add_item_prompt=('NA', 'NA'),
                             del_item_prompt=('NA', 'NA'),
                             tree_header_hidden=True,
                             readonly=True)
            self.parent = parent
            self.conf_namespace = 'files'
            self.schema = [
                {
                    'text': 'Filename',
                    'type': str,
                    'width': 175,
                    'default': '',
                },
                {
                    'text': 'Location',
                    'type': str,
                    # 'visible': False,
                    'stretch': True,
                    'default': '',
                },
                {
                    'text': 'is_dir',
                    'type': bool,
                    'visible': False,
                    'default': False,
                },
            ]

    class Tool_Settings(ConfigJsonToolTree):
        def __init__(self, parent):
            super().__init__(parent=parent,
                             add_item_prompt=('NA', 'NA'),
                             del_item_prompt=('NA', 'NA'),
                             tree_header_hidden=True,
                             readonly=True)
            self.parent = parent
            self.conf_namespace = 'tools'
            self.schema = [
                {
                    'text': 'Tool',
                    'type': str,
                    'width': 175,
                    'default': '',
                },
                {
                    'text': 'id',
                    'visible': False,
                    'default': '',
                },
            ]

# class AgentSettings(ConfigJoined):
#     def __init__(self, parent):
#         super().__init__(parent=parent, layout_type=QVBoxLayout)
#         self.widgets = [
#             self.TopBar(parent=self),
#             self.AgentSettingsPages(parent=self),
#         ]
#
#     class TopBar(ConfigFields):
#         def __init__(self, parent):
#             super().__init__(parent=parent)
#             self.conf_namespace = 'info'
#             self.schema = [
#                 {
#                     'text': 'Avatar',
#                     'key': 'avatar_path',
#                     'type': 'CircularImageLabel',
#                     'diameter': 40,
#                     'default': '',
#                     'label_position': None,
#                     'row_key': 0,
#                 },
#                 {
#                     'text': 'Name',
#                     'type': str,
#                     'default': 'Assistant',
#                     'stretch_x': True,
#                     'text_size': 15,
#                     # 'text_alignment': Qt.AlignCenter,
#                     'label_position': None,
#                     'transparent': True,
#                     'row_key': 0,
#                 },
#                 {
#                     'text': 'Plugin',
#                     'key': 'use_plugin',
#                     'type': 'PluginComboBox',
#                     'label_position': None,
#                     'plugin_type': 'Agent',
#                     'centered': True,
#                     'default': '',
#                     'row_key': 0,
#                 }
#             ]
#
#     # class TopBar(QWidget):
#     #     def __init__(self, parent):
#     #         super().__init__(parent)
#     #
#     #         self.parent = parent
#     #         self.layout = CHBoxLayout(self)
#     #         self.setMouseTracking(True)
#     #
#     #         self.profile_pic_label = QLabel(self)
#     #         self.profile_pic_label.setFixedSize(44, 44)
#     #         self.profile_pic_label.mousePressEvent = self.agent_name_clicked
#     #         self.layout.addWidget(self.profile_pic_label)
#     #
#     #         # self.title_label = QLineEdit(self)
#     #         # self.small_font = self.title_label.font()
#     #         # self.small_font.setPointSize(10)
#     #         # self.title_label.setFont(self.small_font)
#     #         # text_color = self.parent.main.system.config.dict.get('display.text_color', '#c4c4c4')
#     #         # self.title_label.setStyleSheet(f"QLineEdit {{ color: {apply_alpha_to_hex(text_color, 0.90)}; background-color: transparent; }}"
#     #         #                                f"QLineEdit:hover {{ color: {text_color}; }}")
#     #         # self.title_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
#     #         # self.title_label.textChanged.connect(self.title_edited)
#     #         #
#     #         self.agent_name_label = QLineEdit(self)
#     #         self.lbl_font = self.agent_name_label.font()
#     #         self.lbl_font.setPointSize(15)
#     #         self.agent_name_label.setFont(self.lbl_font)
#     #         self.agent_name_label.mousePressEvent = self.agent_name_clicked
#     #         self.agent_name_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
#     #         self.layout.addWidget(self.agent_name_label)
#
#         #     # #######
#         #     #
#         #     # # self.settings_layout = CVBoxLayout(self)
#         #     # #
#         #     # # self.input_container = QWidget()
#         #     # # self.input_container.setFixedHeight(44)
#         #     # # self.topbar_layout = CHBoxLayout(self.input_container)
#         #     # # self.topbar_layout.setContentsMargins(6, 0, 0, 0)
#         #     # #
#         #     # # self.settings_layout.addWidget(self.input_container)
#         #     # #
#         #     # # self.profile_pic_label = QLabel(self)
#         #     # # self.profile_pic_label.setFixedSize(44, 44)
#         #     # #
#         #     # # self.topbar_layout.addWidget(self.profile_pic_label)
#         #     # # # connect profile label click to method 'open'
#         #     # # self.profile_pic_label.mousePressEvent = self.agent_name_clicked
#         #     #
#         #     # self.agent_name_label = QLabel(self)
#         #     #
#         #     # self.lbl_font = self.agent_name_label.font()
#         #     # self.lbl_font.setPointSize(15)
#         #     # self.agent_name_label.setFont(self.lbl_font)
#         #     # self.agent_name_label.mousePressEvent = self.agent_name_clicked
#         #     # self.agent_name_label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
#         #     #
#         #     # self.topbar_layout.addWidget(self.agent_name_label)
#         #     #
#         #     # self.title_label = QLineEdit(self)
#         #     # self.small_font = self.title_label.font()
#         #     # self.small_font.setPointSize(10)
#         #     # self.title_label.setFont(self.small_font)
#         #     # text_color = self.parent.main.system.config.dict.get('display.text_color', '#c4c4c4')
#         #     # self.title_label.setStyleSheet(f"QLineEdit {{ color: {apply_alpha_to_hex(text_color, 0.90)}; background-color: transparent; }}"
#         #     #                                f"QLineEdit:hover {{ color: {text_color}; }}")
#         #     # self.title_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
#         #     # self.title_label.textChanged.connect(self.title_edited)
#         #     #
#         #     # self.topbar_layout.addWidget(self.title_label)
#         #     #
#         #     # self.button_container = QWidget()
#         #     # self.button_layout = QHBoxLayout(self.button_container)
#         #     # self.button_layout.setSpacing(5)
#         #     # # self.button_layout.setContentsMargins(0, 0, 20, 0)
#         #     #
#         #     # # Create buttons
#         #     # self.btn_prev_context = IconButton(parent=self, icon_path=':/resources/icon-left-arrow.png')
#         #     # self.btn_next_context = IconButton(parent=self, icon_path=':/resources/icon-right-arrow.png')
#         #     #
#         #     # self.btn_prev_context.clicked.connect(self.previous_context)
#         #     # self.btn_next_context.clicked.connect(self.next_context)
#         #     #
#         #     # self.btn_info = QPushButton()
#         #     # self.btn_info.setText('i')
#         #     # self.btn_info.setFixedSize(25, 25)
#         #     # self.btn_info.clicked.connect(self.showContextInfo)
#         #     #
#         #     # self.button_layout.addWidget(self.btn_prev_context)
#         #     # self.button_layout.addWidget(self.btn_next_context)
#         #     # self.button_layout.addWidget(self.btn_info)
#         #     #
#         #     # # Add the container to the top bar layout
#         #     # self.topbar_layout.addWidget(self.button_container)
#         #     #
#         #     # self.button_container.hide()
#         #
#         # def load(self):
#         #     try:
#         #         self.agent_name_label.setText(self.parent.workflow.chat_name)
#         #         with block_signals(self.title_label):
#         #             self.title_label.setText(self.parent.workflow.chat_title)
#         #             self.title_label.setCursorPosition(0)
#         #
#         #         member_paths = get_avatar_paths_from_config(self.parent.workflow.config)
#         #         member_pixmap = path_to_pixmap(member_paths, diameter=35)
#         #         self.profile_pic_label.setPixmap(member_pixmap)
#         #     except Exception as e:
#         #         print(e)
#         #         raise e
#         #
#         # def title_edited(self, text):
#         #     sql.execute(f"""
#         #         UPDATE contexts
#         #         SET name = ?
#         #         WHERE id = ?
#         #     """, (text, self.parent.workflow.context_id,))
#         #     self.parent.workflow.chat_title = text
#         #
#         # def showContextInfo(self):
#         #     context_id = self.parent.workflow.context_id
#         #     leaf_id = self.parent.workflow.leaf_id
#         #
#         #     display_messagebox(
#         #         icon=QMessageBox.Warning,
#         #         text=f"Context ID: {context_id}\nLeaf ID: {leaf_id}",
#         #         title="Context Info",
#         #         buttons=QMessageBox.Ok,
#         #     )
#         #
#         # def next_context(self):
#         #     next_context_id = sql.get_scalar("""
#         #         SELECT
#         #             id
#         #         FROM contexts
#         #         WHERE parent_id IS NULL
#         #             AND kind = 'CHAT'
#         #             AND id > ?
#         #         ORDER BY
#         #             id
#         #         LIMIT 1;""", (self.parent.workflow.context_id,))
#         #
#         #     if next_context_id:
#         #         self.parent.goto_context(next_context_id)
#         #         # self.parent.load()
#         #         self.btn_prev_context.setEnabled(True)
#         #     else:
#         #         self.btn_next_context.setEnabled(False)
#         #
#         # def previous_context(self):
#         #     prev_context_id = sql.get_scalar("""
#         #         SELECT
#         #             id
#         #         FROM contexts
#         #         WHERE parent_id IS NULL
#         #             AND kind = 'CHAT'
#         #             AND id < ?
#         #         ORDER BY
#         #             id DESC
#         #         LIMIT 1;""", (self.parent.workflow.context_id,))
#         #     if prev_context_id:
#         #         self.parent.goto_context(prev_context_id)
#         #         # self.parent.load()
#         #         self.btn_next_context.setEnabled(True)
#         #     else:
#         #         self.btn_prev_context.setEnabled(False)
#         #
#         # def enterEvent(self, event):
#         #     self.button_container.show()
#         #
#         # def leaveEvent(self, event):
#         #     self.button_container.hide()
#         #
#         # def agent_name_clicked(self, event):
#         #     if not self.parent.workflow_settings.isVisible():
#         #         self.parent.workflow_settings.show()
#         #         self.parent.workflow_settings.load()
#         #     else:
#         #         self.parent.workflow_settings.hide()
#
#     class AgentSettingsPages(ConfigPages):
#         def __init__(self, parent):
#             super().__init__(parent=parent)
#             self.main = find_main_widget(parent)
#             self.member_type = 'agent'
#             self.member_id = None
#             self.layout.addSpacing(10)
#
#             self.pages = {
#                 'Info': self.Info_Settings(self),
#                 'Chat': self.Chat_Settings(self),
#                 # 'Files': self.File_Settings(self),
#                 'Tools': self.Tool_Settings(self),
#             }
#
#         @abstractmethod
#         def save_config(self):
#             """Saves the config to database when modified"""
#             pass
#
#         class Info_Settings(ConfigJoined):
#             def __init__(self, parent):
#                 super().__init__(parent=parent, layout_type=QVBoxLayout)
#                 self.widgets = [
#                     self.Info_Fields(parent=self),
#                 ]
#
#             class Info_Fields(ConfigFields):
#                 def __init__(self, parent):
#                     super().__init__(parent=parent)
#                     self.conf_namespace = 'info'
#                     self.alignment = Qt.AlignHCenter
#                     self.schema = [
#                         {
#                             'text': 'Avatar',
#                             'key': 'avatar_path',
#                             'type': 'CircularImageLabel',
#                             'default': '',
#                             'label_position': None,
#                         },
#                         {
#                             'text': 'Name',
#                             'type': str,
#                             'default': 'Assistant',
#                             'stretch_x': True,
#                             'text_size': 15,
#                             'text_alignment': Qt.AlignCenter,
#                             'label_position': None,
#                             'transparent': True,
#                         },
#                         {
#                             'text': 'Plugin',
#                             'key': 'use_plugin',
#                             'type': 'PluginComboBox',
#                             'label_position': None,
#                             'plugin_type': 'Agent',
#                             'centered': True,
#                             'default': '',
#                         }
#                     ]
#
#         class Chat_Settings(ConfigTabs):
#             def __init__(self, parent):
#                 super().__init__(parent=parent)
#
#                 self.pages = {
#                     'Messages': self.Page_Chat_Messages(parent=self),
#                     'Preload': self.Page_Chat_Preload(parent=self),
#                     'Output': self.Page_Chat_Output(parent=self),
#                     'Blocks': self.Page_Chat_Blocks(parent=self),
#                     'Group': self.Page_Chat_Group(parent=self),
#                     # 'Voice': self.Page_Chat_Voice(parent=self),
#                 }
#
#             class Page_Chat_Messages(ConfigFields):
#                 def __init__(self, parent):
#                     super().__init__(parent=parent)
#                     from src.system.base import manager
#                     self.conf_namespace = 'chat'
#                     self.schema = [
#                         {
#                             'text': 'Model',
#                             'type': 'ModelComboBox',
#                             'default': '',  # convert_model_json_to_obj(manager.config.dict.get('system.default_chat_model', 'mistral/mistral-large-latest')),  # 'mistral/mistral-large-latest',
#                             'row_key': 0,
#                         },
#                         {
#                             'text': 'Display markdown',
#                             'type': bool,
#                             'default': True,
#                             'row_key': 0,
#                         },
#                         {
#                             'text': 'System message',
#                             'key': 'sys_msg',
#                             'type': str,
#                             'num_lines': 12,
#                             'default': '',
#                             'stretch_x': True,
#                             'gen_block_folder_id': 4,
#                             'stretch_y': True,
#                             'label_position': 'top',
#                         },
#                         {
#                             'text': 'Max messages',
#                             'type': int,
#                             'minimum': 1,
#                             'maximum': 99,
#                             'default': 10,
#                             'width': 60,
#                             'has_toggle': True,
#                             'row_key': 1,
#                         },
#                         {
#                             'text': 'Max turns',
#                             'type': int,
#                             'minimum': 1,
#                             'maximum': 99,
#                             'default': 7,
#                             'width': 60,
#                             'has_toggle': True,
#                             'row_key': 1,
#                         },
#                     ]
#
#             class Page_Chat_Preload(ConfigJsonTree):
#                 def __init__(self, parent):
#                     super().__init__(parent=parent,
#                                      add_item_prompt=('NA', 'NA'),
#                                      del_item_prompt=('NA', 'NA'))
#                     self.conf_namespace = 'chat.preload'
#                     self.schema = [
#                         {
#                             'text': 'Role',
#                             'type': 'RoleComboBox',
#                             'width': 120,
#                             'default': 'assistant',
#                         },
#                         {
#                             'text': 'Content',
#                             'type': str,
#                             'stretch': True,
#                             'wrap_text': True,
#                             'default': '',
#                         },
#                         {
#                             'text': 'Type',
#                             'type': ('Normal', 'Context', 'Welcome'),
#                             'width': 90,
#                             'default': 'Normal',
#                         },
#                     ]
#
#             class Page_Chat_Output(ConfigJsonTree):
#                 def __init__(self, parent):
#                     super().__init__(parent=parent,
#                                      add_item_prompt=('NA', 'NA'),
#                                      del_item_prompt=('NA', 'NA'))
#                     self.conf_namespace = 'chat.output'
#                     self.schema = [
#                         {
#                             'text': 'XML Tag',
#                             'type': str,
#                             'stretch': True,
#                             'default': '',
#                         },
#                         {
#                             'text': 'Map to role',
#                             'type': 'RoleComboBox',
#                             'width': 120,
#                             'default': 'assistant',
#                         },
#                     ]
#
#             class Page_Chat_Blocks(ConfigJsonTree):
#                 def __init__(self, parent):
#                     super().__init__(parent=parent,
#                                      add_item_prompt=('NA', 'NA'),
#                                      del_item_prompt=('NA', 'NA'))
#                     self.conf_namespace = 'blocks'
#                     self.schema = [
#                         {
#                             'text': 'Placeholder',
#                             'type': str,
#                             'width': 120,
#                             'default': '< Placeholder >',
#                         },
#                         {
#                             'text': 'Value',
#                             'type': str,
#                             'stretch': True,
#                             'wrap_text': True,
#                             'default': '',
#                         },
#                     ]
#
#             class Page_Chat_Group(ConfigFields):
#                 def __init__(self, parent):
#                     super().__init__(parent=parent)
#                     self.conf_namespace = 'group'
#                     self.label_width = 175
#                     self.schema = [
#                         {
#                             'text': 'Hide bubbles',
#                             'type': bool,
#                             'tooltip': 'When checked, the responses from this member will not be shown in the chat',
#                             'default': False,
#                         },
#                         {
#                             'text': 'Output placeholder',
#                             'type': str,
#                             'tooltip': 'A tag to use this member\'s output from other members system messages',
#                             'default': '',
#                         },
#                         {
#                             'text': 'On multiple inputs',
#                             'type': ('Append to system msg', 'Merged user message', 'Reply individually'),
#                             'tooltip': 'How to handle multiple inputs from the user (Not implemented yet)',
#                             'default': 'Merged user message',
#                         },
#                         {
#                             'text': 'Show members as user role',
#                             'type': bool,
#                             'default': True,
#                         },
#                         {
#                             'text': 'Member description',
#                             'type': str,
#                             'num_lines': 4,
#                             # 'label_position': 'top',
#                             'stretch_x': True,
#                             'tooltip': 'A description of the member that can be used by other members (Not implemented yet)',
#                             'default': '',
#                         }
#                     ]
#
#             # class Page_Chat_Voice(ConfigVoiceTree):
#             #     def __init__(self, parent):
#             #         super().__init__(parent=parent)
#
#         class File_Settings(ConfigJsonFileTree):
#             def __init__(self, parent):
#                 self.IS_DEV_MODE = True
#                 super().__init__(parent=parent,
#                                  add_item_prompt=('NA', 'NA'),
#                                  del_item_prompt=('NA', 'NA'),
#                                  tree_header_hidden=True,
#                                  readonly=True)
#                 self.parent = parent
#                 self.conf_namespace = 'files'
#                 self.schema = [
#                     {
#                         'text': 'Filename',
#                         'type': str,
#                         'width': 175,
#                         'default': '',
#                     },
#                     {
#                         'text': 'Location',
#                         'type': str,
#                         # 'visible': False,
#                         'stretch': True,
#                         'default': '',
#                     },
#                     {
#                         'text': 'is_dir',
#                         'type': bool,
#                         'visible': False,
#                         'default': False,
#                     },
#                 ]
#
#         class Tool_Settings(ConfigJsonToolTree):
#             def __init__(self, parent):
#                 super().__init__(parent=parent,
#                                  add_item_prompt=('NA', 'NA'),
#                                  del_item_prompt=('NA', 'NA'),
#                                  tree_header_hidden=True,
#                                  readonly=True)
#                 self.parent = parent
#                 self.conf_namespace = 'tools'
#                 self.schema = [
#                     {
#                         'text': 'Tool',
#                         'type': str,
#                         'width': 175,
#                         'default': '',
#                     },
#                     {
#                         'text': 'id',
#                         'visible': False,
#                         'default': '',
#                     },
#                 ]
