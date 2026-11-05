from typing import Any

from gui import system
from plugins.workflows.members import LlmMember
from utils.helpers import set_module_type, convert_model_json_to_obj


@set_module_type(module_type='Members', plugin='AGENT', settings='agent_settings')
class Agent(LlmMember):
    default_role = 'assistant'
    avatar_key = 'avatar_path'
    default_avatar = ':/resources/icon-agent-solid.png'
    name_key = 'name'
    default_name = 'Assistant'
    workflow_insert_mode = 'list'
    conversational = True
    OUTPUT = Any

    @property
    def INPUTS(self):
        return {
            'MESSAGE': Any,
            'CONFIG': {
                'chat.sys_msg': str,
            },
        }

    @property
    def OUTPUTS(self):
        model_json = self.config.get(self.model_config_key, system.manager.config.get('system.default_chat_model', 'mistral/mistral-large-latest'))
        model_obj = convert_model_json_to_obj(model_json)
        structured_data = model_obj.get('model_params', {}).get('structure.data', [])
        if structured_data:
            type_convs = {'str': str, 'int': int, 'float': float, 'bool': bool}
            structured_data = [p['attribute'] for p in structured_data]
            return {
                'OUTPUT': Any,
                'STRUCTURE': {
                    k: type_convs.get(v, str)
                    for k, v in structured_data
                },
            }
        else:
            return {  # Any  # {
                'OUTPUT': Any,
            }

    def __init__(self, **kwargs):
        super().__init__(**kwargs, model_config_key='chat.model')
        self.name = self.config.get('name', 'Assistant')
        # self.parameters = {  todo
        #     'System message': 'chat.sys_msg',
        #     'Max messages': 'chat.max_messages',
        #     'Max turns': 'chat.max_turns',
        # }

    async def system_message(self, msgs_in_system=None, response_instruction='', msgs_in_system_len=0):
        builtin_blocks = {
            'char_name': self.name,
            'full_name': self.name,
            'response_type': 'response',
            'verb': '',
        }
        formatted_sys_msg = await self.format_config_value(
            'chat.sys_msg', additional_blocks=builtin_blocks)

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