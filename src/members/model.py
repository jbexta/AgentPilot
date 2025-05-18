import base64
import json
import os
import re

from src.gui.widgets import ConfigFields
from src.members.base import Member
from src.utils import sql
from src.utils.filesystem import get_application_path
from src.utils.helpers import convert_model_json_to_obj
from src.utils.media import play_file


class Model(Member):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.receivable_function = self.receive

    # def get_content(self, run_sub_blocks=True):  # todo dupe code 777
    #     from src.system.base import manager
    #     content = self.config.get('data', '')
    #
    #     if run_sub_blocks:
    #         block_type = self.config.get('block_type', 'Text')
    #         nestable_block_types = ['Text', 'Prompt']
    #         if block_type in nestable_block_types:
    #             # # Check for circular references
    #             # if name in visited:
    #             #     raise RecursionError(f"Circular reference detected in blocks: {name}")
    #             # visited.add(name)
    #             content = manager.blocks.format_string(content, ref_workflow=self.workflow)  # additional_blocks=member_blocks_dict)
    #
    #     return content  # manager.blocks.format_string(content, additional_blocks=member_blocks_dict)
    #
    # def default_role(self):  # todo clean
    #     return self.config.get(self.default_role_key, 'block')


class VoiceModel(Model):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def get_content(self, run_sub_blocks=True):  # todo dupe code 777
        # We have to redefine this here because we inherit from LlmMember
        from src.system.base import manager
        content = self.config.get('text', '')

        if run_sub_blocks:
            content = manager.blocks.format_string(content, ref_workflow=self.workflow)

        return content

    async def receive(self):
        """The entry response method for the member."""
        import wave
        from src.system.base import manager  # todo
        model_json = self.config.get('model', manager.config.get('system.default_chat_model', 'mistral/mistral-large-latest'))
        model_obj = convert_model_json_to_obj(model_json)
        text = self.get_content()
        filepath = self.text_to_filepath(text)

        # Buffer all chunks into a single audio stream
        audio_buffer = b""

        if self.config.get('use_cache', False):
            # model id is  in  `log`['model']['model_name']
            last_generated_path = sql.get_scalar("""
                SELECT json_extract(msg, '$.filepath')
                FROM contexts_messages
                WHERE role = 'audio' AND 
                    json_extract(log, '$.text') = ? AND 
                    json_extract(log, '$.model.model_name') = ?
                ORDER BY id DESC
                LIMIT 1""",
                (text, model_obj.get('model_name'))
            )
            if last_generated_path:
                try:
                    with open(last_generated_path, 'rb') as f:
                        audio_buffer = f.read()
                    filepath = last_generated_path

                except Exception:
                    pass

        if not audio_buffer:
            stream = await manager.providers.run_model(
                model_obj=model_obj,
                text=text,
            )

            for chunk in stream:
                audio_buffer += chunk

            # Save the audio to a file with proper WAV headers
            # Default audio parameters - adjust these based on your model's output format
            channels = 1
            sample_width = 2  # 16-bit
            framerate = 16000

            # Create a WAV file with proper headers
            with wave.open(filepath, 'wb') as wav_file:
                wav_file.setnchannels(channels)
                wav_file.setsampwidth(sample_width)
                wav_file.setframerate(framerate)
                wav_file.writeframes(audio_buffer)

        else:
            pass

        logging_obj = {
            'id': 0,
            'context_id': self.workflow.context_id,
            'member_id': self.full_member_id(),
            'model': model_obj,
            'text': text,
        }

        if self.config.get('play_audio', True):
            blocking = self.config.get('wait_until_finished', False)
            wait_percent = self.config.get('wait_percent', 0.0)
            play_file(filepath, blocking=blocking, wait_percent=wait_percent)

        msg_json = {
            'filepath': filepath,
        }
        msg_content = json.dumps(msg_json)
        self.workflow.save_message('audio', msg_content, self.full_member_id(), logging_obj)

        yield 'SYS', 'SKIP'
        # yield 'audio', msg_content
        # # stream = self.realtime_client.stream_realtime(model=model_obj, messages=messages, system_msg=system_msg)
        # #
        # for chunk in stream:
        #     self.play_chunk(chunk)
        #     yield 'audio', chunk
        #
        # if 'api_key' in model_obj['model_params']:
        #     model_obj['model_params'].pop('api_key')
        #
        # #
        # # for key, response in role_responses.items():
        # #     if key == 'tools':
        # #         all_tools = response
        # #         for tool in all_tools:
        # #             tool_args_json = tool['function']['arguments']
        # #             # tool_name = tool_name.replace('_', ' ').capitalize()
        # #             tools = self.main.system.tools.to_dict()
        # #             first_matching_name = next((k for k, v in tools.items()
        # #                                       if convert_to_safe_case(k) == tool['function']['name']),
        # #                                      None)  # todo add duplicate check, or
        # #             first_matching_id = sql.get_scalar("SELECT uuid FROM tools WHERE name = ?",
        # #                                                (first_matching_name,))
        # #             msg_content = json.dumps({  #!toolcall!#
        # #                 'tool_uuid': first_matching_id,
        # #                 'tool_call_id': tool['id'], # str(uuid.uuid4()),  #
        # #                 'name': tool['function']['name'],
        # #                 'args': tool_args_json,
        # #                 'text': tool['function']['name'].replace('_', ' ').capitalize(),
        # #             })
        # #             self.workflow.save_message('tool', msg_content, self.full_member_id(), logging_obj)
        # #     else:
        # #         if response != '':
        # #             self.workflow.save_message(key, response, self.full_member_id(), logging_obj)

    # async def stream(self, model, text):
    #     from src.system.base import manager
    #
    #     stream = await manager.providers.run_model(
    #         model_obj=model,
    #         text=text,
    #     )
    #
    #     async for resp in stream:
    #         pass

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
        base_dir = os.path.join(app_path, 'audio')

        # Ensure directory exists
        os.makedirs(base_dir, exist_ok=True)

        # Try increasing word count if file exists
        while word_limit <= len(words):
            file_name = '_'.join(words[:word_limit])
            file_path = os.path.join(base_dir, f"{file_name}.wav")

            if not os.path.exists(file_path):
                return file_path

            word_limit += 1

        # If all words are used, append numbers
        file_name = '_'.join(words) if words else "audio"
        counter = 2

        while True:
            file_path = os.path.join(base_dir, f"{file_name}_{counter}.wav")
            if not os.path.exists(file_path):
                return file_path
            counter += 1

class ImageModel(Model):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    async def receive(self):
        """The entry response method for the member."""
        # content = self.get_content()
        # yield self.default_role(), content
        # self.workflow.save_message(self.default_role(), content, self.full_member_id())  # , logging_obj)


class VoiceModelSettings(ConfigFields):
    def __init__(self, parent):
        super().__init__(parent=parent)
        self.schema = [
            {
                'text': 'Type',
                'key': 'model_type',
                'type': 'PluginComboBox',
                'plugin_type': 'ModelTypes',
                'allow_none': False,
                'width': 90,
                'default': 'Voice',
                'row_key': 0,
            },
            {
                'text': 'Model',
                'type': 'ModelComboBox',
                'model_kind': 'VOICE',
                # 'default': 'mistral/mistral-large-latest',
                'default': {
                    'kind': 'VOICE',
                    'model_name': '9BWtsMINqrJLrRacOk9x',
                    # 'model_params': {},
                    'provider': 'elevenlabs',
                },
                'row_key': 0,
            },
            {
                'text': 'Text',
                'type': str,
                'label_position': 'top',
                'num_lines': 3,
                'stretch_x': True,
                'stretch_y': True,
                'default': '',
            },
            {
                'text': 'Play audio',
                'type': bool,
                'default': True,
                'row_key': 1,
            },
            {
                'text': 'Use cache',
                'type': bool,
                'default': False,
                'row_key': 1,
            },
            {
                'text': 'Wait until finished',
                'type': bool,
                'default': False,
                'row_key': 1,
            },
            # {
            #     'text': 'Member options',
            #     'type': 'MemberPopupButton',
            #     'use_namespace': 'group',
            #     'member_type': 'voice',
            #     'label_position': None,
            #     'default': '',
            #     'row_key': 0,
            # },
        ]


class ImageModelSettings(ConfigFields):
    def __init__(self, parent):
        super().__init__(parent=parent)
        self.schema = [
            {
                'text': 'Type',
                'key': 'model_type',
                'type': 'PluginComboBox',
                'plugin_type': 'ModelTypes',
                'allow_none': False,
                'width': 90,
                'default': 'Voice',
                'row_key': 0,
            },
            {
                'text': 'Model',
                'type': 'ModelComboBox',
                'model_kind': 'IMAGE',
                # 'default': 'mistral/mistral-large-latest',
                'row_key': 0,
            },
            # {
            #     'text': 'Member options',
            #     'type': 'MemberPopupButton',
            #     'use_namespace': 'group',
            #     'member_type': 'image',
            #     'label_position': None,
            #     'default': '',
            #     'row_key': 0,
            # },
        ]