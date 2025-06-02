
import json
import os
import re
from typing import Any

from src.members import Model
from src.utils import sql
from src.utils.filesystem import get_application_path
from src.utils.helpers import convert_model_json_to_obj, set_module_type
from src.utils.media import play_file


@set_module_type(module_type='Members', plugin='MODEL', settings='voice_model_settings')
class VoiceModel(Model):
    default_role = 'audio'
    default_avatar = ':/resources/icon-voice.png'
    default_name = 'Voice model'
    OUTPUT = 'AUDIO'

    @property
    def INPUTS(self):
        return {
            'CONFIG': {
                'text': Any[str, list[str]],
            },
        }

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def get_content(self, run_sub_blocks=True):  # todo dupe code 777
        # We have to redefine this here because we inherit from LlmMember
        from src.system import manager
        content = self.config.get('text', '')

        if run_sub_blocks:
            content = manager.blocks.format_string(content, ref_workflow=self.workflow)

        return content

    async def receive(self):
        """The entry response method for the member."""
        import wave
        from src.system import manager  # todo
        model_json = self.config.get('model', manager.config.get('system.default_voice_model', 'mistral/mistral-large-latest'))
        model_obj = convert_model_json_to_obj(model_json)
        text = self.get_content()
        filepath = self.text_to_filepath(text)

        # Buffer all chunks into a single audio stream
        audio_buffer = b""

        if self.config.get('use_cache', False):
            # model id is in `log`['model']['model_name']
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
        self.workflow.save_message(self.default_role, msg_content, self.full_member_id(), logging_obj)

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
    #     from src.system import manager
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