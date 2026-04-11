
import json
from abc import abstractmethod
from fnmatch import fnmatch
import os
import re
from typing import Any, AsyncIterable, Dict, List, Optional
import uuid

import pyautogui

# from plugins.realtimeai.modules.client import RealtimeAIClientWrapper

from gui import system as gui_system  # todo rename, naming conflict

from utils.filesystem import get_application_path
from utils import sql
from utils.helpers import convert_model_json_to_obj, convert_to_safe_case, set_module_type


class Member:
    default_role = 'block'
    allow_async = True
    allow_condition = True

    def __init__(self, **kwargs):
        self.main = kwargs.get('main')
        self.workflow = kwargs.get('workflow', None)
        self.config: Dict[str, Any] = kwargs.get('config', {})

        self.member_id: str = kwargs.get('member_id', '1')
        self.loc_x: int = kwargs.get('loc_x', 0)
        self.loc_y: int = kwargs.get('loc_y', 0)
        self.inputs: List[str] = kwargs.get('inputs', [])

        self.last_output: Optional[str] = None
        self.turn_output: Optional[str] = None
        # self.condition_passed: bool = True

        self.receivable_function = None

    def load(self):
        pass

    # def available_blocks(self):
    #     from gui import system as gui_system
    #     all_blocks = system.manager.blocks.to_dict()
    #
    #     if self.workflow:
    #         members = self.workflow.members
    #         member_names = {m_id: member.config.get('info.name', 'Assistant') for m_id, member in members.items()}
    #         member_placeholders = {
    #             m_id: member.config.get('group.output_placeholder', f'{member_names[m_id]}_{str(m_id)}')
    #             for m_id, member in members.items()}
    #         member_last_outputs = {member.member_id: member.last_output for k, member in self.workflow.members.items()
    #                                if member.last_output != ''}
    #         member_blocks = {member_placeholders[k]: v for k, v in member_last_outputs.items() if v is not None}
    #
    #         all_blocks.update(member_blocks)
    #         all_blocks.update(self.workflow.params)  # these can overwrite base blocks
    #
    #     return all_blocks

    async def format_config_value(self, key, default='',
                                   additional_blocks=None):
        """Get a config value, applying Jinja2 rendering."""
        value = self.config.get(key, default)
        if value:
            value = await gui_system.manager.blocks.format_string(
                value,
                ref_workflow=self.workflow,
                additional_blocks=additional_blocks,
            )
        return value

    async def _format_dict(self, d, additional_blocks=None):
        """Format all _format_block_keys in a dict, returning a clean copy."""
        format_keys = d.get('_format_block_keys', [])
        result = {k: v for k, v in d.items()
                  if k != '_format_block_keys'}
        for key in format_keys:
            if isinstance(key, str):
                value = result.get(key, '')
                if value:
                    result[key] = (
                        await gui_system.manager.blocks.format_string(
                            value,
                            ref_workflow=self.workflow,
                            additional_blocks=additional_blocks,
                        ))
            elif isinstance(key, list) and len(key) > 1:
                target = result
                for part in key[:-1]:
                    if part not in target \
                            or not isinstance(target[part], dict):
                        target = None
                        break
                    target[part] = dict(target[part])
                    target = target[part]
                if target is not None:
                    final_key = key[-1]
                    value = target.get(final_key, '')
                    if value:
                        target[final_key] = (
                            await gui_system.manager.blocks
                            .format_string(
                                value,
                                ref_workflow=self.workflow,
                                additional_blocks=additional_blocks,
                            ))
        return result

    async def get_computed_config(self, additional_blocks=None):
        """Return a copy of the config with all format_blocks fields rendered."""
        return await self._format_dict(self.config, additional_blocks)

    async def get_content(self, run_sub_blocks=True):
        if run_sub_blocks:
            content = await self.format_config_value('data')
        else:
            content = self.config.get('data', '')
        return content

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

    async def run(self):
        """The entry response method for the member."""
        # temp_has_looper_inputs = False
        # if hasattr(self, 'inputs') and self.workflow:
        #     inputs = self.workflow.config.get('inputs', [])
        #     any_looper = any(inp.get('config', {}).get('looper', False) for inp in inputs)
        #     if any_looper:
        #         raise NotImplementedError('Loops are not implemented yet. Coming soon.')

        if self.receivable_function:
            async for key, chunk in self.receivable_function():
                if self.workflow:
                    if self.workflow.stop_requested:
                        self.workflow.stop_requested = False
                        break
                    yield key, chunk
                    if self.workflow.chat_widget:
                        self.workflow.chat_widget.new_sentence(key, self.full_member_id(), chunk)
                else:
                    yield key, chunk

                # if self.workflow.chat_widget:
                #     self.workflow.chat_widget.new_sentence(key, self.full_member_id(), chunk)
                # if self.workflow and self.workflow.stop_requested:
                #     self.workflow.stop_requested = False
                #     break
                # yield key, chunk
                # if self.workflow.chat_widget:
                #     self.workflow.chat_widget.new_sentence(key, self.full_member_id(), chunk)
        else:
            yield 'SYS', 'SKIP'  # todo not needed anymore?

    def get_filepath(self, ext):
        """
        Convert text to a filepath for saving audio.
        If the filename already exists, try with more words or append a number.
        """

        # Remove special characters and keep only alphanumeric characters
        model_params = self.config.get('model', {}).get('model_params', {})
        prompt = model_params.get('prompt', str(uuid.uuid4()))
        prompt = re.sub(r'[^a-zA-Z0-9 ]', '', prompt)
        words = prompt.split()

        # Start with 3 words
        word_limit = 3

        app_path = get_application_path()
        base_dir = os.path.join(app_path, self.default_role)

        # Ensure directory exists
        os.makedirs(base_dir, exist_ok=True)

        # Try increasing word count if file exists
        while word_limit <= len(words):
            file_name = '_'.join(words[:word_limit])
            file_path = os.path.join(base_dir, f"{file_name}.{ext}")

            if not os.path.exists(file_path):
                return file_path

            word_limit += 1

        # If all words are used, append numbers
        file_name = '_'.join(words) if words else self.default_role
        counter = 2

        while True:
            file_path = os.path.join(base_dir, f"{file_name}_{counter}.{ext}")
            if not os.path.exists(file_path):
                return file_path
            counter += 1


class LlmMember(Member):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.model_config_key: str = kwargs.get('model_config_key', '')
        self.tools_config_key: str = 'tools.data'

        self.tools_table = {}
        # self.load()
        self.realtime_client = None
        self.receivable_function = self.receive

    # class MemberRealtimeClient:
    #     """
    #     A class to handle the realtime client for the member.
    #     Initializes the realtime client instance.
    #     """
    #     def __init__(self, member, model_obj):
    #         self.member = member
    #         self.model = model_obj
    #         self.audio_handler = AudioHandler()
    #         self.output_audio_queue = asyncio.Queue()
    #         self.client = RealtimeClient(
    #             # on_text_delta=lambda text: print(f"\nAssistant: {text}", end="", flush=True),
    #             on_audio_delta=lambda audio: self.on_audio_delta(audio),  # self.audio_handler.play_audio(audio),
    #             # on_input_transcript=lambda transcript: self.on_input_transcript(transcript),
    #             # on_output_transcript=lambda transcript: print(f"{transcript}", end="", flush=True),
    #             on_interrupt=lambda: self.audio_handler.stop_playback_immediately(),
    #             turn_detection_mode=TurnDetectionMode.SERVER_VAD,
    #             # tools=tools,
    #         )
    #
    #     def load(self):
    #         from gui import system as gui_system
    #         model_params = system.manager.providers.get_model_parameters(self.model)
    #         api_key = model_params.get('api_key', None)
    #         voice = None
    #         temperature = None
    #         turn_detection_mode = None
    #         instructions = None
    #         self.client.api_key = api_key
    #
    #     # def on_text_delta(self, text):
    #     #     print(f"\nAssistant: {text}", end="", flush=True)
    #
    #     # def on_input_transcript(self, transcript):
    #     #     print(f"\nYou said: {transcript}\nAssistant: ", end="", flush=True)
    #
    #     # def on_output_transcript(self, transcript):
    #     #     print(f"{transcript}", end="", flush=True)
    #
    #     def on_audio_delta(self, audio):
    #         self.output_audio_queue.put_nowait(audio)
    #         self.audio_handler.play_audio(audio)
    #
    #     async def stream_realtime(self, model, messages):
    #         try:
    #             await self.client.connect()
    #             asyncio.create_task(self.client.handle_messages())
    #
    #             # Create a queue to store incoming text deltas
    #             output_transcript_queue = asyncio.Queue()
    #             self.output_audio_queue = asyncio.Queue()  # clear queue
    #
    #             self.client.on_output_transcript = lambda text: output_transcript_queue.put_nowait(text)
    #             # self.client.on_audio_delta = lambda audio: output_audio_queue.put_nowait(audio)
    #             # Send the message to the realtime client
    #             await self.client.send_text('who are you')
    #
    #             responding = True
    #             while responding or not output_transcript_queue.empty():
    #                 try:
    #                     # Wait for text deltas with a timeout
    #                     text = await asyncio.wait_for(output_transcript_queue.get(), timeout=1.0)
    #                     yield self.member.default_role(), text
    #                 except asyncio.TimeoutError:
    #                     responding = False
    #
    #             all_audio_bytes = []
    #             while not self.output_audio_queue.empty():
    #                 audio_bytes = await self.output_audio_queue.get()
    #                 all_audio_bytes.append(audio_bytes)
    #
    #             # Combine all audio bytes
    #             all_audio = b''.join(all_audio_bytes)
    #
    #             # Write audio to WAV file
    #             with wave.open('/home/jb/Documents/output.wav', 'wb') as wav_file:
    #                 # Set parameters (adjust these based on your audio format)
    #                 n_channels = 1
    #                 sample_width = 2  # Assuming 16-bit audio
    #                 frame_rate = 24000  # Adjust this to match your audio's sample rate
    #                 n_frames = len(all_audio) // (n_channels * sample_width)
    #                 comp_type = 'NONE'
    #                 comp_name = 'not compressed'
    #
    #                 wav_file.setparams((n_channels, sample_width, frame_rate, n_frames, comp_type, comp_name))
    #                 wav_file.writeframes(all_audio)
    #
    #             base64_audio = base64.b64encode(all_audio).decode('utf-8')
    #             # # write audio to file
    #             # with open('/home/jb/Documents/output.wav', 'wb') as f:
    #             #     for audio in all_audio_bytes:
    #             #         f.write(audio)
    #             #     f.flush()
    #             # all_audio = b''.join(all_audio_bytes)
    #             # str_all_audio = all_audio.decode('utf-8')
    #             yield 'audio', base64_audio
    #
    #         except Exception as e:
    #             raise e
    #
    # # class MemberRealtimeClient:
    # #     """
    # #     A class to handle the realtime client for the member.
    # #     Initializes the realtime client instance.
    # #     """
    # #     def __init__(self, member, model_obj):
    # #         self.member = member
    # #         self.model = model_obj
    # #         self.audio_handler = AudioHandler()
    # #         self.output_audio_queue = asyncio.Queue()
    # #         self.client = RealtimeClient(
    # #             # on_text_delta=lambda text: print(f"\nAssistant: {text}", end="", flush=True),
    # #             on_audio_delta=lambda audio: self.on_audio_delta(audio),  # self.audio_handler.play_audio(audio),
    # #             # on_input_transcript=lambda transcript: self.on_input_transcript(transcript),
    # #             # on_output_transcript=lambda transcript: print(f"{transcript}", end="", flush=True),
    # #             on_interrupt=lambda: self.audio_handler.stop_playback_immediately(),
    # #             turn_detection_mode=TurnDetectionMode.SERVER_VAD,
    # #             # tools=tools,
    # #         )
    # #
    # #     def load(self):
    # #         from gui import system as gui_system
    # #         model_params = system.manager.providers.get_model_parameters(self.model)
    # #         api_key = model_params.get('api_key', None)
    # #         voice = None
    # #         temperature = None
    # #         turn_detection_mode = None
    # #         instructions = None
    # #         self.client.api_key = api_key
    # #
    # #     # def on_text_delta(self, text):
    # #     #     print(f"\nAssistant: {text}", end="", flush=True)
    # #
    # #     # def on_input_transcript(self, transcript):
    # #     #     print(f"\nYou said: {transcript}\nAssistant: ", end="", flush=True)
    # #
    # #     # def on_output_transcript(self, transcript):
    # #     #     print(f"{transcript}", end="", flush=True)
    # #
    # #     def on_audio_delta(self, audio):
    # #         self.output_audio_queue.put_nowait(audio)
    # #         self.audio_handler.play_audio(audio)
    # #
    # #     async def stream_realtime(self, model, messages):
    # #         try:
    # #             await self.client.connect()
    # #             asyncio.create_task(self.client.handle_messages())
    # #
    # #             # Create a queue to store incoming text deltas
    # #             output_transcript_queue = asyncio.Queue()
    # #             self.output_audio_queue = asyncio.Queue()  # clear queue
    # #
    # #             self.client.on_output_transcript = lambda text: output_transcript_queue.put_nowait(text)
    # #             # self.client.on_audio_delta = lambda audio: output_audio_queue.put_nowait(audio)
    # #             # Send the message to the realtime client
    # #             await self.client.send_text('who are you')
    # #
    # #             responding = True
    # #             while responding or not output_transcript_queue.empty():
    # #                 try:
    # #                     # Wait for text deltas with a timeout
    # #                     text = await asyncio.wait_for(output_transcript_queue.get(), timeout=1.0)
    # #                     yield self.member.default_role(), text
    # #                 except asyncio.TimeoutError:
    # #                     responding = False
    # #
    # #             all_audio_bytes = []
    # #             while not self.output_audio_queue.empty():
    # #                 audio_bytes = await self.output_audio_queue.get()
    # #                 all_audio_bytes.append(audio_bytes)
    # #
    # #             # Combine all audio bytes
    # #             all_audio = b''.join(all_audio_bytes)
    # #
    # #             # Write audio to WAV file
    # #             with wave.open('/home/jb/Documents/output.wav', 'wb') as wav_file:
    # #                 # Set parameters (adjust these based on your audio format)
    # #                 n_channels = 1
    # #                 sample_width = 2  # Assuming 16-bit audio
    # #                 frame_rate = 24000  # Adjust this to match your audio's sample rate
    # #                 n_frames = len(all_audio) // (n_channels * sample_width)
    # #                 comp_type = 'NONE'
    # #                 comp_name = 'not compressed'
    # #
    # #                 wav_file.setparams((n_channels, sample_width, frame_rate, n_frames, comp_type, comp_name))
    # #                 wav_file.writeframes(all_audio)
    # #
    # #             base64_audio = base64.b64encode(all_audio).decode('utf-8')
    # #             # # write audio to file
    # #             # with open('/home/jb/Documents/output.wav', 'wb') as f:
    # #             #     for audio in all_audio_bytes:
    # #             #         f.write(audio)
    # #             #     f.flush()
    # #             # all_audio = b''.join(all_audio_bytes)
    # #             # str_all_audio = all_audio.decode('utf-8')
    # #             yield 'audio', base64_audio
    # #
    # #         except Exception as e:
    # #             raise e

    def load(self):
        self.load_tools()

        model_json = self.config.get(self.model_config_key, gui_system.manager.config.get('system.default_chat_model', 'mistral/mistral-large-latest'))
        model_obj = convert_model_json_to_obj(model_json)

        if model_obj['_model_name'].startswith('gpt-4o-realtime'):
            pass  # todo
            # # Initialize the realtime client
            # if not self.realtime_client:
            #     self.realtime_client = RealtimeAIClientWrapper(self)
            # self.realtime_client.load(model_obj)

    def load_tools(self):
        agent_tools_ids = self.config.get(self.tools_config_key, [])
        # agent_tools_ids = [tool['id'] for tool in tools_in_config]
        if len(agent_tools_ids) == 0:
            return

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
    async def system_message(self, msgs_in_system=None, response_instruction='', msgs_in_system_len=0):
        return ''

    # def default_role(self):  # todo clean
    #     return self.config.get(self.default_role_key, 'assistant')

    @abstractmethod
    async def get_messages(self):  # todo
        return self.workflow.message_history.get_llm_messages(calling_member_id=self.full_member_id())

    async def receive(self):
        model_json = self.config.get(self.model_config_key, gui_system.manager.config.get('system.default_chat_model', 'mistral/mistral-large-latest'))
        model_obj = convert_model_json_to_obj(model_json)
        structured_data = model_obj.get('model_params', {}).get('structure.data', [])

        if self.config.get('computer_use.enabled', False):
            if not getattr(self, '_computer_use_browser', None):
                from plugins.computer_use.utils.desktop import (
                    ComputerUseDesktop,
                )
                grace = self.config.get(
                    'computer_use.grace_period', 3.0
                )
                self._computer_use_browser = ComputerUseDesktop(
                    grace_period=grace,
                )
                await self._computer_use_browser.launch()

        messages = await self.get_messages()
        system_msg = await self.system_message()

        if model_obj['_model_name'].startswith('gpt-4o-realtime'):  # temp todo
            # raise NotImplementedError('Realtime models are not implemented yet.')
            stream = self.realtime_client.stream_realtime(model=model_obj, messages=messages, system_msg=system_msg)
        else:
            if system_msg != '':
                messages.insert(0, {'role': 'system', 'content': system_msg})
            if len(structured_data) > 0:
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
            'id': 0,
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
                    first_matching_name = next((k for k, v in gui_system.manager.tools.items()
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
        tools = self.get_function_call_tools()

        xml_tag_roles = model.get('model_params', {}).get('xml_roles.data', [])
        xml_tag_roles = {tag_dict['xml_tag']: tag_dict['map_to_role'] for tag_dict in xml_tag_roles}
        # default_role = self.config.get(self.default_role_key, 'assistant')
        processor = CharProcessor(tag_roles=xml_tag_roles, default_role=self.default_role)

        stream = await gui_system.manager.models.run_model(
            model_obj=model,
            messages=messages,
            tools=tools
        )
        collected_tools = []

        is_aiter = isinstance(stream, AsyncIterable)
        if is_aiter:
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
        else:  # this is used when falling back to non-streaming response, patch for openai
            message = stream.choices[0].message.content
            yield 'text', message

        if len(collected_tools) > 0:
            if self.config.get('computer_use.enabled', False):
                computer_tools = [
                    t for t in collected_tools
                    if t.get('function', {}).get('name') == 'computer'
                ]
                regular_tools = [
                    t for t in collected_tools
                    if t.get('function', {}).get('name') != 'computer'
                ]
                if computer_tools:
                    async for role, chunk in self._handle_computer_use(
                        model, messages, computer_tools, tools
                    ):
                        yield role, chunk
                if regular_tools:
                    yield 'tools', regular_tools
            else:
                yield 'tools', collected_tools

    async def _handle_computer_use(
        self, model, messages, computer_tool_calls, all_tools
    ):
        """Execute computer use actions inline and continue the loop."""
        browser = self._computer_use_browser
        max_iter = self.config.get('computer_use.max_iterations', 50)

        from plugins.computer_use.widgets.overlay import (
            ComputerUseOverlay,
        )
        overlay = ComputerUseOverlay()
        browser.overlay = overlay
        overlay.show_overlay()
        browser.start_esc_listener()

        try:
            async for key, chunk in self._computer_use_loop(
                browser, model, messages, computer_tool_calls,
                all_tools, max_iter,
            ):
                yield key, chunk
        finally:
            browser.stop_esc_listener()
            overlay.hide_overlay()
            overlay.deleteLater()
            browser.overlay = None

    async def _computer_use_loop(
        self, browser, model, messages, computer_tool_calls,
        all_tools, max_iter,
    ):
        """Inner computer use loop, separated for try/finally in caller."""
        iteration = 0

        while computer_tool_calls and iteration < max_iter:
            iteration += 1

            for tool_call in computer_tool_calls:
                action = json.loads(
                    tool_call['function']['arguments']
                )
                yield 'computer_action', json.dumps(action)

                if self.workflow and self.workflow.stop_requested:
                    browser.cancelled = True
                    return

                screenshot_b64 = await browser.execute_action(action)

                if browser.cancelled:
                    return

                messages.append({
                    'role': 'assistant',
                    'tool_calls': [{
                        'id': tool_call['id'],
                        'type': 'function',
                        'function': {
                            'name': 'computer',
                            'arguments': json.dumps(action),
                        },
                    }],
                })
                messages.append({
                    'role': 'tool',
                    'tool_call_id': tool_call['id'],
                    'content': [{
                        'type': 'image_url',
                        'image_url': {
                            'url': (
                                f'data:image/png;base64,'
                                f'{screenshot_b64}'
                            ),
                        },
                    }],
                })

            if self.workflow and self.workflow.stop_requested:
                return

            stream = await gui_system.manager.models.run_model(
                model_obj=model,
                messages=messages,
                tools=all_tools,
            )
            collected_tools = []
            accumulated_text = ''
            is_aiter = isinstance(stream, AsyncIterable)
            if is_aiter:
                async for resp in stream:
                    delta = resp.choices[0].get('delta', {})
                    if not delta:
                        continue
                    content = delta.get('content', None) or ''
                    tool_calls = delta.get('tool_calls', None)
                    if tool_calls:
                        for t_chunk in delta.tool_calls:
                            if len(collected_tools) <= t_chunk.index:
                                collected_tools.append({
                                    "id": "",
                                    "type": "function",
                                    "function": {
                                        "name": "",
                                        "arguments": "",
                                    },
                                })
                            tc = collected_tools[t_chunk.index]
                            if t_chunk.id:
                                tc["id"] += t_chunk.id
                            if t_chunk.function.name:
                                tc["function"]["name"] += (
                                    t_chunk.function.name
                                )
                            if t_chunk.function.arguments:
                                tc["function"]["arguments"] += (
                                    t_chunk.function.arguments
                                )
                    if content != '':
                        accumulated_text += content
            else:
                message = stream.choices[0].message.content
                if message:
                    accumulated_text += message

            computer_tool_calls = [
                t for t in collected_tools
                if t.get('function', {}).get('name') == 'computer'
            ]
            regular_tools = [
                t for t in collected_tools
                if t.get('function', {}).get('name') != 'computer'
            ]
            if regular_tools:
                yield 'tools', regular_tools

        if accumulated_text:
            yield 'text', accumulated_text

    async def stream_structured_output(self, model, messages):
        tools = self.get_function_call_tools()
        provider = gui_system.manager.providers.get(model['provider'])
        if not provider:
            raise ValueError(f"Provider '{model['provider']}' not found.")
        resp = await provider.get_structured_output(
            model_obj=model,
            messages=messages,
            tools=tools,
        )
        yield 'STRUCT', str(resp)
        # return resp

    def get_function_call_tools(self):
        formatted_tools = []
        for tool_id, tool_name, tool_config in self.tools_table:
            tool_config = json.loads(tool_config)

            tool_type = tool_config.get('type', '')
            if tool_type == '':
                tool_type = 'function'

            if tool_type == 'function':
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
            # elif tool_type.startswith('computer_'):
            #     screen_width, screen_height = pyautogui.size()
            #     formatted_tools.append(
            #         {
            #             'type': tool_type,
            #             'function': {
            #                 'name': 'computer',
            #                 'parameters': {
            #                     'display_height_px': screen_height,
            #                     'display_width_px': screen_width,
            #                     'display_number': 1,
            #                 }
            #             }
            #         }
            #     )

            # formatted_tools.append(
            #     {
            #         'type': 'function',
            #         'function': {
            #             'name': convert_to_safe_case(tool_name),
            #             'description': tool_config.get('description', ''),
            #             'parameters': transformed_parameters
            #         }
            #     }
            # )

        if self.config.get('computer_use.enabled', False):
            screen_width = self._computer_use_browser.target_w
            screen_height = self._computer_use_browser.target_h
            formatted_tools.append({
                'type': 'function',
                'function': {
                    'name': 'computer',
                    'description': (
                        f'Control a desktop computer. The screen is '
                        f'{screen_width}x{screen_height} pixels. '
                        f'Coordinates in actions must be within this '
                        f'range. After each action a screenshot is '
                        f'returned. When the task is complete, respond '
                        f'with text instead of calling this tool.'
                    ),
                    'parameters': {
                        'type': 'object',
                        'properties': {
                            'action': {
                                'type': 'string',
                                'enum': [
                                    'left_click', 'right_click',
                                    'middle_click', 'double_click',
                                    'triple_click', 'type', 'key',
                                    'scroll', 'mouse_move', 'drag',
                                    'screenshot', 'cursor_position',
                                ],
                                'description': (
                                    'The action to perform.'
                                ),
                            },
                            'coordinate': {
                                'type': 'array',
                                'items': {'type': 'integer'},
                                'minItems': 2,
                                'maxItems': 2,
                                'description': (
                                    '[x, y] pixel coordinate for '
                                    'click/scroll/move actions.'
                                ),
                            },
                            'text': {
                                'type': 'string',
                                'description': (
                                    'Text to type (for "type" action)'
                                    ' or key combo (for "key" action).'
                                ),
                            },
                            'direction': {
                                'type': 'string',
                                'enum': [
                                    'up', 'down', 'left', 'right',
                                ],
                                'description': (
                                    'Scroll direction (for "scroll").'
                                ),
                            },
                            'amount': {
                                'type': 'integer',
                                'description': (
                                    'Scroll amount (for "scroll").'
                                ),
                            },
                            'start_coordinate': {
                                'type': 'array',
                                'items': {'type': 'integer'},
                                'minItems': 2,
                                'maxItems': 2,
                                'description': (
                                    'Start [x, y] for drag action.'
                                ),
                            },
                            'end_coordinate': {
                                'type': 'array',
                                'items': {'type': 'integer'},
                                'minItems': 2,
                                'maxItems': 2,
                                'description': (
                                    'End [x, y] for drag action.'
                                ),
                            },
                        },
                        'required': ['action'],
                    },
                },
            })

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


class Block(Member):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.receivable_function = self.receive


class Model(Member):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.receivable_function = self.receive
    
    def text_to_filepath(self, text):
        """
        Convert text to a filepath for saving audio.
        If the filename already exists, try with more words or append a number.
        """

        # Remove special characters and keep only alphanumeric characters
        text = re.sub(r'[^a-zA-Z0-9 ]', '', text)
        words = text.split()

        # Start with 3 words
        word_limit = 3
        app_path = get_application_path()
        base_dir = os.path.join(app_path, self.default_role)

        # Ensure directory exists
        os.makedirs(base_dir, exist_ok=True)

        if self.default_role == 'audio':
            ext = 'wav'
        elif self.default_role == 'video':
            ext = 'mp4'

        # Try increasing word count if file exists
        while word_limit <= len(words):
            file_name = '_'.join(words[:word_limit])
            file_path = os.path.join(base_dir, f"{file_name}.{ext}")

            if not os.path.exists(file_path):
                return file_path

            word_limit += 1

        # If all words are used, append numbers
        file_name = '_'.join(words) if words else self.default_role
        counter = 2

        while True:
            file_path = os.path.join(base_dir, f"{file_name}_{counter}.wav")
            if not os.path.exists(file_path):
                return file_path
            counter += 1


class CharProcessor:  # todo clean / rethink
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
        self.active_tag_role = None
        self.tag_text_buffer = ''
        self.current_char = None

    def match_tag(self, tag):
        return next((role for pattern, role in self.tag_roles.items() if fnmatch(tag.lower(), pattern.lower().replace('%', '*'))), None)

    async def process_chunk(self, chunk):
        if chunk is None:
            async for item in self.process_char(None):  # todo hack to get last char
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
            elif char == '>' and self.tag_opened:
                self.tag_opened = False
                matched_role = self.match_tag(self.tag_name_buffer)
                if matched_role:
                    self.active_tag = self.tag_name_buffer
                    self.active_tag_role = matched_role
                else:
                    yield self.default_role, f'<{self.tag_name_buffer}>'
                self.tag_name_buffer = ''
            elif self.tag_opened:
                self.tag_name_buffer += char
                is_alnum = char.isalnum() or char in ['-', '_', ' ']
                if not is_alnum:
                    yield self.default_role, f'<{self.tag_name_buffer}'  # intentionally missing end bracket
                    self.tag_name_buffer = ''
                    self.tag_opened = False
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
                    self.active_tag_role = None
                    # yield self.default_role, f'</{self.closing_tag_name_buffer}>'
                else:
                    yield self.active_tag_role, f'</{self.closing_tag_name_buffer}>'
                self.closing_tag_name_buffer = ''
            elif self.closing_tag_opened:
                if char == '/' and self.closing_tag_name_buffer == '':
                    return
                self.closing_tag_name_buffer += char
                is_alnum = char.isalnum() or char in ['-', '_']
                if not is_alnum:
                    yield self.active_tag_role, f'</{self.closing_tag_name_buffer}'  # intentionally missing end bracket
                    self.closing_tag_opened = False
                    self.closing_tag_name_buffer = ''

            else:
                yield self.active_tag_role, char

        if next_char is None:
            if self.tag_name_buffer != '':
                yield self.default_role, f'<{self.tag_name_buffer}'
            if self.closing_tag_name_buffer != '':
                yield self.active_tag_role, f'</{self.closing_tag_name_buffer}'
            return


class MediaMember(Member):
    """Base class for media members (Image, Video, Audio).

    Subclasses must define:
        default_role: str - 'image', 'video', or 'audio'
    """
    workflow_insert_mode = 'single'

    @property
    def INPUTS(self):
        return {
            'CONFIG': {
                'text': str,
            },
        }

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.receivable_function = self.receive

    async def receive(self):
        """The entry response method for the member."""
        msg_content = await self._process_media()
        yield 'SYS', 'SKIP'

    async def _process_media(self):
        """Shared media processing logic. Returns msg_content."""
        config = await self.get_computed_config()
        model_obj = None
        filepath = config.get('browse.path', None)

        if filepath:
            msg_json = {
                'filepath': filepath,
            }
        else:
            mode = config.get('mode', 'Model')

            if mode == 'Model':
                model_json = config.get('model', None)
                if not model_json:
                    raise ValueError("Model is required")
                model_obj = convert_model_json_to_obj(model_json)
                model_params = model_obj.get('model_params', None)

                if config.get('use_cache', False):
                    candidates = sql.get_results("""
                        SELECT json_extract(msg, '$.filepath'),
                               json_extract(log, '$.model.model_params')
                        FROM contexts_messages
                        WHERE role = ? AND
                            COALESCE(json_extract(log, '$.model._model_name'), json_extract(log, '$.model.model_name')) = ? AND
                            json_extract(msg, '$.filepath') IS NOT NULL
                        ORDER BY id DESC
                        LIMIT 20""",
                        (self.default_role, model_obj.get('_model_name'))
                    )
                    last_generated_path = None
                    for cached_path, cached_params_str in candidates:
                        cached_params = json.loads(cached_params_str) if cached_params_str else {}
                        if all(cached_params.get(k) == v for k, v in model_params.items()):
                            last_generated_path = cached_path
                            break
                    if last_generated_path:
                        filepath = last_generated_path
                        msg_json = {'filepath': filepath}

                if not filepath:
                    msg_json = None
                    stream = await gui_system.manager.models.run_model(
                        model_obj=model_obj,
                    )
                    for item in stream:
                        msg_json = json.loads(item)
                        break

                    if config.get('wait_until_finished', False) \
                            and msg_json and 'request_id' in msg_json:
                        import asyncio
                        from utils.helpers import download_url_to_file
                        request_id = msg_json['request_id']
                        model_name = msg_json['model_name']
                        provider_name = msg_json['provider']
                        provider = gui_system.manager.providers.get(provider_name)
                        while True:
                            status = await provider.get_request_status(model_name, request_id)
                            if status.get('status') == 'completed':
                                break
                            elif status.get('status') == 'failed':
                                raise RuntimeError(f"Media generation failed for {model_name}")
                            await asyncio.sleep(2)
                        media_urls = await provider.get_request_result(model_name, request_id)
                        if media_urls:
                            filepath = await download_url_to_file(media_urls[0])
                            msg_json = {'filepath': filepath}

            elif mode == 'URL':
                raise NotImplementedError("URL mode not implemented")
            else:
                raise ValueError("Invalid mode")

        logging_obj = {
            'id': 0,
            'context_id': self.workflow.context_id,
            'member_id': self.full_member_id(),
        }
        if model_obj:
            if 'api_key' in model_obj['model_params']:
                model_obj['model_params'].pop('api_key')
            logging_obj['model'] = model_obj

        msg_content = json.dumps(msg_json)
        self.workflow.save_message(self.default_role, msg_content, self.full_member_id(), logging_obj)
        return msg_content
