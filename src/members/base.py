import json
from abc import abstractmethod
from fnmatch import fnmatch

from src.plugins.openairealtimeclient.src import AudioHandler, InputHandler, RealtimeClient
# from src.system.base import manager
from src.utils import sql
from src.utils.helpers import convert_model_json_to_obj, convert_to_safe_case


class Member:
    def __init__(self, **kwargs):
        self.main = kwargs.get('main')
        self.workflow = kwargs.get('workflow', None)
        self.config = kwargs.get('config', {})

        self.member_id = kwargs.get('member_id', '1')
        self.loc_x = kwargs.get('loc_x', 0)
        self.loc_y = kwargs.get('loc_y', 0)
        self.inputs = kwargs.get('inputs', [])
        # self.allowed_inputs = []

        self.last_output = None
        self.turn_output = None
        self.response_task = None

        self.default_role_key = 'group.output_role'
        self.receivable_function = None

    def load(self):
        pass

    def allowed_inputs(self):
        return {'Flow': None}

    def allowed_outputs(self):
        return {'Output': str}

    def full_member_id(self):
        # bubble up to the top level workflow collecting member ids, return as a string joined with "." and reversed
        # where self._parent_workflow is None, that's the top level workflow
        id_list = [self.member_id]
        parent = self.workflow  #_parent_workflow
        while parent:
            if getattr(parent, '_parent_workflow', None) is None:
                break
            id_list.append(parent.member_id)
            parent = parent.workflow
        return '.'.join(map(str, reversed(id_list)))

    def allowed_inputs(self):
        return {'Flow': None}

    @abstractmethod
    async def run_member(self):
        """The entry response method for the member."""
        temp_has_looper_inputs = False
        if hasattr(self, 'inputs') and self.workflow:
            inputs = self.workflow.config.get('inputs', [])
            any_looper = any(inp.get('config', {}).get('looper', False) for inp in inputs)
            if any_looper:
                raise NotImplementedError('Loops are not implemented yet. Coming soon.')

        if self.receivable_function:
            async for key, chunk in self.receivable_function():
                if self.workflow and self.workflow.stop_requested:
                    self.workflow.stop_requested = False
                    break

                yield key, chunk
                if self.main:
                    self.main.new_sentence_signal.emit(key, self.full_member_id(), chunk)
        else:
            yield 'SYS', 'SKIP'


class LlmMember(Member):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.model_config_key = kwargs.get('model_config_key', '')
        self.tools_config_key = 'tools.data'

        # Realtime client
        self.audio_handler = AudioHandler()
        self.realtime_client = None

        self.tools_table = {}
        # self.load()

        self.receivable_function = self.receive

    def allowed_inputs(self):
        return {'Flow': None, 'Message': None}

    def allowed_outputs(self):
        return {'Output': str}

    def load(self):
        self.load_tools()

        from src.system.base import manager  # todo
        model_json = self.config.get(self.model_config_key, manager.config.dict.get('system.default_chat_model', 'mistral/mistral-large-latest'))
        model_obj = convert_model_json_to_obj(model_json)

        if model_obj['model_name'].startswith('gpt-4o-realtime'):
            # Initialize the realtime client
            self.realtime_client = RealtimeClient(
                on_text_delta=lambda text: print(f"\nAssistant: {text}", end="", flush=True),
                on_audio_delta=lambda audio: self.audio_handler.play_audio(audio),
                on_input_transcript=lambda transcript: print(f"\nYou said: {transcript}\nAssistant: ", end="",
                                                             flush=True),
                on_output_transcript=lambda transcript: print(f"{transcript}", end="", flush=True),
                # tools=tools,
            )

    def load_tools(self):
        agent_tools_ids = json.loads(self.config.get(self.tools_config_key, '[]'))
        # agent_tools_ids = [tool['id'] for tool in tools_in_config]
        if len(agent_tools_ids) == 0:
            return []

        self.tools_table = sql.get_results(f"""
            SELECT
                uuid,
                name,
                config
            FROM tools
            WHERE 
                uuid IN ({','.join(['?'] * len(agent_tools_ids))})
        """, agent_tools_ids)

    @abstractmethod
    def system_message(self, msgs_in_system=None, response_instruction='', msgs_in_system_len=0):
        return ''

    @abstractmethod
    def get_messages(self):  #todo
        return self.workflow.message_history.get_llm_messages(calling_member_id=self.full_member_id())

    async def receive(self):
        from src.system.base import manager  # todo
        messages = self.get_messages()

        system_msg = self.system_message()
        if system_msg != '':
            messages.insert(0, {'role': 'system', 'content': system_msg})

        model_json = self.config.get(self.model_config_key, manager.config.dict.get('system.default_chat_model', 'mistral/mistral-large-latest'))
        model_obj = convert_model_json_to_obj(model_json)
        structured = True

        if model_obj['model_name'].startswith('gpt-4o-realtime'):  # temp todo
            # raise NotImplementedError('Realtime models are not implemented yet.')
            stream = self.stream_realtime(model=model_obj, messages=messages)
        elif structured:
            stream = self.stream_structured_output(model=model_obj, messages=messages)
        else:
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
                    msg_content = json.dumps({  #!toolcall!#
                        'tool_uuid': first_matching_id,
                        'tool_call_id': tool['id'], # str(uuid.uuid4()),  #
                        'name': tool['function']['name'],
                        'args': tool_args_json,
                        'text': tool['function']['name'].replace('_', ' ').capitalize(),
                    })
                    self.workflow.save_message('tool', msg_content, self.full_member_id(), logging_obj)
            else:
                if response != '':
                    self.workflow.save_message(key, response, self.full_member_id(), logging_obj)

    async def stream(self, model, messages):
        from src.system.base import manager
        tools = self.get_function_call_tools()

        xml_tag_roles = json.loads(model.get('model_params', {}).get('xml_roles.data', '[]'))
        xml_tag_roles = {tag_dict['xml_tag'].lower(): tag_dict['map_to_role'] for tag_dict in xml_tag_roles}
        default_role = self.config.get(self.default_role_key, 'assistant')
        processor = CharProcessor(tag_roles=xml_tag_roles, default_role=default_role)

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
                    yield role, content
        async for role, content in processor.process_chunk(None):
            yield role, content  # todo to get last char

        if len(collected_tools) > 0:
            yield 'tools', collected_tools

    async def stream_structured_output(self, model, messages):
        from src.system.base import manager
        tools = self.get_function_call_tools()
        resp = await manager.providers.get_structured_output(
            model_obj=model,
            messages=messages,
            tools=tools
        )
        yield 'STRUCT', str(resp)
        # return resp

    async def stream_realtime(self, model, messages):
        if not self.realtime_client:
            raise ValueError('Realtime client not initialized.')

        await self.realtime_client.connect()

    def get_function_call_tools(self):
        formatted_tools = []
        for tool_id, tool_name, tool_config in self.tools_table:
            tool_config = json.loads(tool_config)
            parameters_data = tool_config.get('params', [])
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
        transformed = {
            'type': 'object',
            'properties': {},
            'required': []
        }

        # Iterate through each parameter and convert it
        for parameter in parameters_data:
            param_name = convert_to_safe_case(parameter['name'])
            param_desc = parameter['description']
            param_type = parameter['type'].lower()
            param_required = parameter['req']
            # param_default = parameter['default']

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


class CharProcessor:
    def __init__(self, tag_roles=None, default_role='assistant'):
        self.default_role = default_role
        self.tag_roles = tag_roles or {}
        self.tag_opened = False
        self.closing_tag_opened = False
        self.tag_name_buffer = ''
        self.closing_tag_name_buffer = ''
        self.text_buffer = ''
        self.active_tags = []  # = None
        self.active_tag = None
        self.tag_text_buffer = ''
        self.current_char = None

    def match_tag(self, tag):
        return next((role for pattern, role in self.tag_roles.items() if fnmatch(tag.lower(), pattern.lower().replace('%', '*'))), None)

    async def process_chunk(self, chunk):
        if chunk is None:
            async for item in self.process_char(None):  # hack to get last char
                yield item
            return

        for char in chunk:
            self.text_buffer += char
            async for item in self.process_char(char):
                yield item

    async def process_char(self, next_char):
        char = self.current_char
        self.current_char = next_char
        if not char:
            return

        if not self.active_tag:
            if char == '<':
                self.tag_opened = True
            elif char == '>':
                self.tag_opened = False
                matched_role = self.match_tag(self.tag_name_buffer.lower())
                if matched_role:
                    self.active_tag = self.tag_name_buffer
                yield self.default_role, f'<{self.tag_name_buffer}>'
                self.tag_name_buffer = ''
            elif self.tag_opened:
                self.tag_name_buffer += char
            else:
                yield self.default_role, char

        elif self.active_tag:
            if next_char == '/' and char == '<':
                self.closing_tag_opened = True
            elif char == '>' and self.closing_tag_opened:
                self.closing_tag_opened = False
                self.closing_tag_name_buffer = self.closing_tag_name_buffer.strip('/')
                if self.closing_tag_name_buffer == self.active_tag:
                    self.active_tag = None
                    yield self.default_role, f'</{self.closing_tag_name_buffer}>'
                else:
                    yield self.active_tag.lower(), f'</{self.closing_tag_name_buffer}>'
                self.closing_tag_name_buffer = ''
            elif self.closing_tag_opened:
                self.closing_tag_name_buffer += char
            else:
                yield self.active_tag.lower(), char

        if next_char is None:
            return