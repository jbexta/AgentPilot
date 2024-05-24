import json
import re
import time
import string
import asyncio
from queue import Queue
from src.utils import helpers, llm
from src.members.base import Member

from abc import abstractmethod

from PySide6.QtWidgets import *
from PySide6.QtGui import Qt

from src.utils.helpers import display_messagebox
from src.utils import sql

from src.gui.config import ConfigPages, ConfigFields, ConfigTabs, ConfigJsonTree, \
    ConfigJoined, ConfigJsonFileTree, ConfigPlugin, ConfigJsonToolTree
from src.gui.widgets import IconButton, find_main_widget


class Agent(Member):
    def __init__(self, **kwargs):  # main=None, agent_id=0, member_id=None, config=None, workflow=None, wake=False, inputs=None):
        super().__init__(**kwargs)  #  main=main, workflow=workflow, m_id=member_id, inputs=inputs)
        self.workflow = kwargs.get('workflow')  #workflow
        self.id = kwargs.get('agent_id')
        self.member_id = kwargs.get('member_id')
        self.name = ''
        self.desc = ''
        self.speaker = None
        self.voice_data = None
        self.config = kwargs.get('config', {})
        self.name = self.config.get('info.name', 'Assistant')
        self.instance_config = {}

        self.tools_config = {}
        self.tools = {}

        self.intermediate_task_responses = Queue()
        self.speech_lock = asyncio.Lock()

        self.logging_obj = None
        # self.active_task = None

        self.bg_task = None
        # if wake:
        #     self.bg_task = self.workflow.loop.create_task(self.wake())

    async def wake(self):
        bg_tasks = [
            # self.speaker.download_voices(),
            # self.speaker.speak_voices(),
            # # self.__intermediate_response_thread(),
            # # self.loop.create_task(self.listener.listen())
        ]
        await asyncio.gather(*bg_tasks)

    def __del__(self):
        if self.bg_task:
            self.bg_task.cancel()

    # async def __intermediate_response_thread(self):
    #     while True:
    #         await asyncio.sleep(0.03)
    #         if self.speech_lock.locked():
    #             continue
    #         if self.intermediate_task_responses.empty():
    #             continue
    #
    #         async with self.speech_lock:
    #             response_str = self.format_message(self.intermediate_task_responses.get())
    #             self.get_response(extra_prompt=response_str,
    #                               check_for_tasks=False)

    def load_agent(self):
        pass
        # # # logging.debug(f'LOAD AGENT {self.id}')
        # # if len(self.config) > 0:
        # #     return
        # if self.member_id:
        #     agent_data = sql.get_results("""
        #         SELECT
        #             cm.`agent_config`,
        #             s.`value` AS `default_agent`
        #         FROM contexts_members cm
        #         LEFT JOIN settings s
        #             ON s.field = 'default_agent'
        #         WHERE cm.id = ? """, (self.member_id,))[0]
        # elif self.id > 0:
        #     agent_data = sql.get_results("""
        #         SELECT
        #             a.`config`,
        #             s.`value` AS `default_agent`
        #         FROM agents a
        #         LEFT JOIN settings s ON s.field = 'default_agent'
        #         WHERE a.id = ? """, (self.id,))[0]
        # else:
        #     agent_data = sql.get_results("""
        #         SELECT
        #             '{}',
        #             s.`value` AS `default_agent`
        #         FROM settings s
        #         WHERE s.field = 'default_agent' """)[0]  todo
        # agent_data = ['{}', '{}']
        #
        # agent_config = json.loads(agent_data[0])
        # default_agent = json.loads(agent_data[1])
        # self.config = {**default_agent, **agent_config}
        # self.name = self.config.get('info.name', 'Assistant')

        # found_instance_config = {k.replace('instance.', ''): v for k, v in self.config.items() if
        #                         k.startswith('instance.')}
        # self.instance_config = {**self.instance_config, **found_instance_config}  # todo

        # voice_id = self.config.get('voice.current_id', None)
        # if voice_id is not None and str(voice_id) != '0':  # todo dirty
        #     self.voice_data = sql.get_results("""
        #         SELECT
        #             v.id,
        #             v.api_id,
        #             v.uuid,
        #             v.display_name,
        #             v.known_from,
        #             v.creator,
        #             v.lang,
        #             v.verb
        #         FROM voices v
        #         WHERE v.id = ? """, (voice_id,))[0]
        # else:
        #     self.voice_data = None
        #
        # self.load_tools()

        # if self.speaker is not None: self.speaker.kill()
        # self.speaker = None  # speech.Stream_Speak(self)  todo

    def load_tools(self):
        tools_in_config = json.loads(self.config.get('tools.data', '[]'))
        agent_tools_ids = [tool['id'] for tool in tools_in_config]
        if len(agent_tools_ids) == 0:
            return []

        self.tools_config = sql.get_results(f"""
            SELECT
                name,
                config
            FROM tools
            WHERE 
                -- json_extract(config, '$.method') = ? AND
                id IN ({','.join(['?'] * len(agent_tools_ids))})
        """, agent_tools_ids)

        for tool_name, tool_config in self.tools_config:
            tool_config = json.loads(tool_config)
            code = tool_config.get('code.data', None)
            method = tool_config.get('code.type', '')

            try:
                if method == 'Imported':
                    exec_globals = {}
                    exec(code, exec_globals)
                    imported_tool = exec_globals.get('tool')
                    if imported_tool is not None:
                        self.tools[tool_name] = imported_tool
                else:
                    pass
            except Exception as e:
                print(f'Error loading tool {tool_name}: {e}')

        # self.tools = {tool_name: json.loads(tool_config) for tool_name, tool_config in tools}
        # return tools

    # todo move block formatter to helpers, and implement in crewai
    def system_message(self, msgs_in_system=None, response_instruction='', msgs_in_system_len=0):
        date = time.strftime("%a, %b %d, %Y", time.localtime())
        time_ = time.strftime("%I:%M %p", time.localtime())
        timezone = time.strftime("%Z", time.localtime())
        location = "Sheffield, UK"

        # todo - 0.3.0 - Link to new all member configs
        # member_names = {k: v.get('info.name', 'Assistant') for k, v in self.workflow.member_configs.items()}
        # member_placeholders = {k: v.get('group.output_context_placeholder', f'{member_names[k]}_{str(k)}')
        #                        for k, v in self.workflow.member_configs.items()}
        # member_last_outputs = {member.m_id: member.last_output for k, member in self.workflow.members.items() if member.last_output != ''}
        member_blocks_dict = {}  # {member_placeholders[k]: v for k, v in member_last_outputs.items()}
        context_blocks_dict = {k: v for k, v in self.workflow.main.system.blocks.to_dict().items()}

        blocks_dict = helpers.SafeDict({**member_blocks_dict, **context_blocks_dict})

        semi_formatted_sys_msg = string.Formatter().vformat(
            self.config.get('chat.sys_msg', ''), (), blocks_dict,
        )

        agent_name = self.config.get('info.name', 'Assistant')
        if self.voice_data:
            char_name = re.sub(r'\([^)]*\)', '', self.voice_data[3]).strip()
            full_name = f"{char_name} from {self.voice_data[4]}" if self.voice_data[4] != '' else char_name
            verb = self.voice_data[7]
            if verb != '': verb = ' ' + verb
        else:
            char_name = agent_name
            full_name = agent_name
            verb = ''

        # ungrouped_actions = [fk for fk, fv in retrieval.all_category_files['_Uncategorised'].all_actions_data.items()]
        # action_groups = [k for k, v in retrieval.all_category_files.items() if not k.startswith('_')]
        all_actions = []  # ungrouped_actions + action_groups

        response_type = self.config.get('chat.response_type', 'response')  # todo

        # Use the SafeDict class to format the text to gracefully allow non existent keys
        final_formatted_sys_msg = string.Formatter().vformat(
            semi_formatted_sys_msg, (), helpers.SafeDict(
                agent_name=agent_name,
                char_name=char_name,
                full_name=full_name,
                verb=verb,
                actions=', '.join(all_actions),
                response_instruction=response_instruction.strip(),
                date=date,
                time=time_,
                timezone=timezone,
                location=location,
                response_type=response_type
            )
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

        return final_formatted_sys_msg + response_instruction + message_str

    def format_message(self, message):
        dialogue_placeholders = {
            '[RES]': '[ITSOC] very briefly respond to the user in no more than [3S] ',
            '[INF]': '[ITSOC] very briefly inform the user in no more than [3S] ',
            '[ANS]': '[ITSOC] very briefly respond to the user considering the following information: ',
            '[Q]': '[ITSOC] Ask the user the following question: ',
            '[SAY]': '[ITSOC], say: ',
            '[MI]': '[ITSOC] Ask for the following information: ',
            '[ITSOC]': 'In the style of {char_name}{verb}, spoken like a genuine dialogue ',
            '[WOFA]': 'Without offering any further assistance, ',
            '[3S]': 'Three sentences',
        }
        for k, v in dialogue_placeholders.items():
            message = message.replace(k, v)

        if message != '':
            message = f"[INSTRUCTIONS-FOR-NEXT-RESPONSE]\n{message}\n[/INSTRUCTIONS-FOR-NEXT-RESPONSE]"
        return message

    async def run_member(self):
        """The entry response method for the member."""
        for key, chunk in self.receive(stream=True):
            if self.workflow.stop_requested:
                self.workflow.stop_requested = False
                break
            # if key == 'assistant':
            self.main.new_sentence_signal.emit(key, self.member_id, chunk)

    def receive(self, stream=False):
        return self.get_response_stream() if stream else self.get_response()

    def get_response(self):
        response = ''
        for key, chunk in self.get_response_stream():
            response += chunk or ''
        return response

    def get_response_stream(self, extra_prompt='', msgs_in_system=False):
        messages = self.workflow.message_history.get(llm_format=True, calling_member_id=self.member_id)
        use_msgs_in_system = messages if msgs_in_system else None
        system_msg = self.system_message(msgs_in_system=use_msgs_in_system,
                                         response_instruction=extra_prompt)
        model_name = self.config.get('chat.model', 'gpt-3.5-turbo')
        model = (model_name, self.workflow.main.system.models.get_llm_parameters(model_name))

        kwargs = dict(messages=messages, msgs_in_system=msgs_in_system, system_msg=system_msg, model=model)
        stream = self.stream(**kwargs)

        # response = ''
        role_responses = {}

        for key, chunk in stream:
            if key not in role_responses:
                role_responses[key] = ''
            if key == 'tools':
                role_responses['tools'] = chunk
            else:
                chunk = chunk or ''
                role_responses[key] += chunk
                yield key, chunk
            # if key == 'assistant':
            #     response += chunk or ''
            #     yield key, chunk

            # elif key == 'tools':
            #     all_tools = chunk
            #     for tool_name, tool_args in all_tools.items():
            #         tool_name = tool_name.replace('_', ' ').capitalize()
            #         self.workflow.save_message('tool', tool_name, self.member_id, self.logging_obj)
            # else:

        for key, response in role_responses.items():
            if key == 'tools':
                all_tools = response
                for tool_name, tool_args in all_tools.items():
                    tool_name = tool_name.replace('_', ' ').capitalize()
                    self.workflow.save_message('tool', tool_name, self.member_id, self.logging_obj)
            # elif key == 'code':
            #     response =
            else:
                if response != '':
                    self.workflow.save_message(key, response, self.member_id, self.logging_obj)
        #
        # if response != '':
        #     self.workflow.save_message('assistant', response, self.member_id, self.logging_obj)

    def stream(self, messages, msgs_in_system=False, system_msg='', model=None):
        tools = self.get_function_call_tools()
        stream = llm.get_chat_response(messages if not msgs_in_system else [],
                                       system_msg,
                                       model_obj=model,
                                       tools=tools)
        self.logging_obj = stream.logging_obj

        collected_tools = {}
        current_tool_name = None
        current_args = ''

        for resp in stream:
            delta = resp.choices[0].get('delta', {})
            if not delta:
                continue
            tool_calls = delta.get('tool_calls', None)
            content = delta.get('content', '')
            if tool_calls:
                tool_name = tool_calls[0].function.name
                if tool_name:
                    if current_tool_name is not None:
                        collected_tools[current_tool_name] = current_args
                    current_tool_name = tool_name
                    current_args = ''
                else:
                    current_args += tool_calls[0].function.arguments

            else:
                yield 'assistant', content or ''

        if current_tool_name is not None:
            collected_tools[current_tool_name] = current_args

        if len(collected_tools) > 0:
            yield 'tools', collected_tools
        # else:
        #     raise NotImplementedError('No message or tool calls were returned from the model')

    # def get_agent_tools(self):
    #     agent_tools = json.loads(self.config.get('tools.data', '[]'))
    #     agent_tools_ids = [tool['id'] for tool in agent_tools]
    #     if len(agent_tools_ids) == 0:
    #         return []
    #
    #     tools = sql.get_results(f"""
    #         SELECT
    #             name,
    #             config
    #         FROM tools
    #         WHERE
    #             -- json_extract(config, '$.method') = ? AND
    #             id IN ({','.join(['?'] * len(agent_tools_ids))})
    #     """, agent_tools_ids)
    #
    #     return tools

    def get_function_call_tools(self):
        formatted_tools = []
        for tool_name, tool_config in self.tools_config:
            tool_config = json.loads(tool_config)
            parameters_data = tool_config.get('parameters.data', '[]')
            transformed_parameters = self.transform_parameters(parameters_data)

            formatted_tools.append(
                {
                    'type': 'function',
                    'function': {
                        'name': tool_name.lower().replace(' ', '_'),
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
            param_name = parameter['name'].lower().replace(' ', '_')
            param_desc = parameter['description']
            param_type = parameter['type'].lower()
            param_required = parameter['req']
            param_default = parameter['default']

            transformed['properties'][param_name] = {
                'type': param_type,
                'description': param_desc,
            }
            if param_required:
                transformed['required'].append(param_name)

        return transformed

    # def update_instance_config(self, field, value):
    #     self.instance_config[field] = value
    #     sql.execute(f"""UPDATE contexts_members SET agent_config = json_set(agent_config, '$."instance.{field}"', ?) WHERE id = ?""",
    #                 (value, self.member_id))

    # def combine_lang_and_code(self, lang, code):
    #     return f'```{lang}\n{code}\n```'
    # def __wait_until_finished_speaking(self):
    #     while True:
    #         if not self.speaker.speaking: break
    #         time.sleep(0.05)


class AgentSettings(ConfigPages):
    def __init__(self, parent):  # , is_context_member_agent=False):
        super().__init__(parent=parent)
        # self.parent = parent
        self.main = find_main_widget(parent)
        self.member_type = 'agent'
        self.member_id = None
        # self.is_context_member_agent = is_context_member_agent
        self.ref_id = None
        self.layout.addSpacing(10)

        self.pages = {
            'Info': self.Info_Settings(self),
            'Chat': self.Chat_Settings(self),
            'Files': self.File_Settings(self),
            'Tools': self.Tool_Settings(self),
            # 'Voice': self.Voice_Settings(self),
        }
        # self.build_schema()

    @abstractmethod
    def save_config(self):
        """Saves the config to database when modified"""
        pass
        # # # todo - ignore instance keys

    class Info_Settings(ConfigJoined):
        def __init__(self, parent):
            super().__init__(parent=parent, layout_type=QVBoxLayout)
            self.widgets = [
                self.Info_Fields(parent=self),
                self.Info_Plugin(parent=self),
            ]

        class Info_Fields(ConfigFields):
            def __init__(self, parent):
                super().__init__(parent=parent)
                self.parent = parent
                self.namespace = 'info'
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
                        'width': 400,
                        'text_size': 15,
                        'text_alignment': Qt.AlignCenter,
                        'label_position': None,
                        'transparent': True,
                        'fill_width': True,
                    },
                ]

        class Info_Plugin(ConfigPlugin):
            def __init__(self, parent):
                super().__init__(
                    parent=parent,
                    plugin_type='Agent',
                    namespace='plugin',
                    plugin_json_key='info.use_plugin'
                )

    class Chat_Settings(ConfigTabs):
        def __init__(self, parent):
            super().__init__(parent=parent)

            self.pages = {
                'Messages': self.Page_Chat_Messages(parent=self),
                'Preload': self.Page_Chat_Preload(parent=self),
                'Blocks': self.Page_Chat_Blocks(parent=self),
                'Group': self.Page_Chat_Group(parent=self),
            }

        class Page_Chat_Messages(ConfigFields):
            def __init__(self, parent):
                super().__init__(parent=parent)
                self.parent = parent
                self.namespace = 'chat'
                self.schema = [
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

        class Page_Chat_Preload(ConfigJsonTree):
            def __init__(self, parent):
                super().__init__(parent=parent,
                                 add_item_prompt=('NA', 'NA'),
                                 del_item_prompt=('NA', 'NA'))
                self.parent = parent
                self.namespace = 'chat.preload'
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

        class Page_Chat_Blocks(ConfigJsonTree):
            def __init__(self, parent):
                super().__init__(parent=parent,
                                 add_item_prompt=('NA', 'NA'),
                                 del_item_prompt=('NA', 'NA'))
                self.parent = parent
                self.namespace = 'blocks'
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
                self.parent = parent
                self.namespace = 'group'
                self.label_width = 175
                self.schema = [
                    {
                        'text': 'Hide responses',
                        'type': bool,
                        'tooltip': 'When checked, the responses from this member will not be shown in the chat (Not implemented yet)',
                        'default': False,
                    },
                    {
                        'text': 'Output placeholder',
                        'type': str,
                        'tooltip': 'A tag to refer to this member\'s output from other members system messages',
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
                        'width': 320,
                        'tooltip': 'A description of the member that can be used by other members (Not implemented yet)',
                        'default': '',
                    }
                ]

    class File_Settings(ConfigJsonFileTree):
        def __init__(self, parent):
            super().__init__(parent=parent,
                             add_item_prompt=('NA', 'NA'),
                             del_item_prompt=('NA', 'NA'),
                             tree_header_hidden=True,
                             readonly=True)
            self.parent = parent
            self.namespace = 'files'
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
            self.namespace = 'tools'
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
