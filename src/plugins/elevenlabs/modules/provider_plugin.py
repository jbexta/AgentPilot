import json
import os
import tempfile
import time

from PySide6.QtWidgets import QMessageBox

from src.gui.config import ConfigFields
from src.utils import sql
import requests

from src.utils.helpers import display_message_box, convert_model_json_to_obj
from src.system.providers import Provider

from elevenlabs.client import ElevenLabs

cookie = None

# # rate limit 1 reqper sec
# thread_lock = asyncio.Lock()


class ElevenLabsProvider(Provider):
    def __init__(self, parent, api_id):
        super().__init__(parent=parent)
        self.api_id = api_id
        self.visible_tabs = ['Voice']

        api_key = sql.get_scalar("SELECT api_key FROM apis WHERE id = ?", (api_id,))
        kwargs = {}
        if api_key.startswith('$'):
            api_key = os.environ.get(api_key[1:], '')  # todo clean
        if api_key != '':  # todo clean
            kwargs['api_key'] = api_key
        self.client = ElevenLabs(**kwargs)

    def get_model(self, model_obj):  # kind, model_name):
        kind, model_name = model_obj.get('kind'), model_obj.get('model_name')
        return self.models.get((kind, model_name), {})

    def get_model_stream(self, model_obj, **kwargs):
        model_obj = convert_model_json_to_obj(model_obj)
        voice_id = model_obj.get('model_name', None)
        if not voice_id:
            raise ValueError("Voice ID is required")

        text = kwargs['text']
        audio_stream = self.client.text_to_speech.convert_as_stream(
            text=text,
            voice_id=voice_id,
            model_id="eleven_multilingual_v2",
            output_format="pcm_16000",
        )

        return audio_stream

    async def run_model(self, model_obj, **kwargs):  # todo rename all run_model to get_model_stream
        return self.get_model_stream(model_obj, **kwargs)

    def get_model_parameters(self, model_obj, incl_api_data=True):
        kind, model_name = model_obj.get('kind'), model_obj.get('model_name')
        if kind == 'CHAT':
            accepted_keys = [
                'temperature',
                'top_p',
                'presence_penalty',
                'frequency_penalty',
                'max_tokens',
            ]
            if incl_api_data:
                accepted_keys.extend([
                    'api_key',
                    'api_base',
                    'api_version',
                    'custom_provider',
                ])
        else:
            accepted_keys = []

        model_config = self.models.get((kind, model_name), {})
        cleaned_model_config = {k: v for k, v in model_config.items() if k in accepted_keys}
        return cleaned_model_config

    def play_stream(self, stream):
        import sounddevice as sd
        import numpy as np
        import io
        import wave
        # from scipy.io import wavfile

        # We need a temporary file to store the complete audio
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_file:
            temp_path = temp_file.name
            for chunk in stream.iter_chunks():
                if not chunk:
                    continue

                # Write to file for complete audio
                temp_file.write(chunk)

                # Play the chunk in real-time todo deduper
                try:
                    with io.BytesIO(chunk) as chunk_io:
                        with wave.open(chunk_io, 'rb') as wave_file:
                            framerate = wave_file.getframerate()
                            data = np.frombuffer(wave_file.readframes(wave_file.getnframes()), dtype=np.int16)
                            sd.play(data, framerate)
                            sd.wait()
                except Exception as e:
                    print(f"Error playing chunk: {e}")

        return temp_path

    class VoiceModelParameters(ConfigFields):
        def __init__(self, parent):
            super().__init__(parent=parent)
            self.parent = parent
            self.schema = [
                {
                    'text': 'Model name',
                    'type': str,
                    'label_width': 125,
                    'width': 265,
                    'tooltip': 'The name of the model to send to the API',
                    'default': '',
                },
            ]

    def sync_voice(self):
        retval = display_message_box(
            icon=QMessageBox.Warning,
            title="Sync voices",
            text="Are you sure you want to sync ElevenLabs voices?",
            buttons=QMessageBox.Yes | QMessageBox.No,
        )
        if retval != QMessageBox.Yes:
            return

        try:
            model_cnt = self.sync_all_voices()

            display_message_box(
                icon=QMessageBox.Information,
                title="Success",
                text=f"Synced {model_cnt} voices",  # and {folder_cnt} folders."
            )
        except Exception as e:
            display_message_box(
                icon=QMessageBox.Critical,
                title="Error syncing voices",
                text=f"An error occurred while syncing voices: {e}"
            )

    def sync_all_voices(self):
        existing_uids = sql.get_results(
            """
            SELECT json_extract(config, '$.model_id')
            FROM models
            WHERE api_id = ?""",
            (self.api_id,),
            return_type='list'
        )

        response = self.client.voices.get_all()

        models = response.voices

        if len(models) == 0:
            return 0

        params = [
            (self.api_id, model.name, json.dumps({
                'model_name': model.voice_id,
                'preview_url': model.preview_url,
            }))
            for model in models if model.voice_id not in existing_uids
        ]
        flat_params = tuple([item for sublist in params for item in sublist])
        sql.execute(f"""
            INSERT INTO models (
                api_id,
                kind,
                name,
                config
            )
            VALUES {', '.join(['(?, "VOICE", ?, ?)' 
            for model in models if model.voice_id not in existing_uids])}
        """, flat_params)

        return len(models)


    # def try_download_voice(self, speech_uuid):
    #     if not speech_uuid: return None
    #     url = f"https://api.fakeyou.com/tts/job/{speech_uuid}"
    #     headers = {
    #         "content-type": "application/json",
    #         "credentials": "include",
    #         "cookie": f"session={cookie}"
    #     }
    #     try_count = 0
    #     while True:
    #         try:
    #             # with thread_lock:
    #             #     while time.time() - last_req < 1:
    #             #         time.sleep(0.1)
    #             #     last_req = time.time()
    #             response = requests.get(url, headers=headers)
    #             if response.status_code != 200:
    #                 raise ConnectionError()
    #
    #             path = response.json()['state']['maybe_public_bucket_wav_audio_path']
    #             if not path: raise Exception("No path")
    #
    #             audio_request = requests.get(f'https://storage.googleapis.com/vocodes-public{path}')
    #             with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_file:
    #                 temp_file.write(audio_request.content)
    #                 return temp_file.name
    #
    #         except Exception as e:
    #             time.sleep(0.1)
    #             try_count += 1
    #             if try_count > 10:
    #                 print(f"Failed to download {speech_uuid}")
    #                 return None
    #
    #
    # # def generate_voice_async(voice_uuid, text):
    # #     global last_req
    # #     url = 'https://api.fakeyou.com/tts/inference'
    # #     headers = {
    # #         "content-type": "application/json",
    # #         "credentials": "include",
    # #         "cookie": f"session={cookie}"
    # #     }
    # #     data = {
    # #         'tts_model_token': voice_uuid,
    # #         'uuid_idempotency_token': str(uuid4()),
    # #         'inference_text': text
    # #     }
    # #     try:
    # #         # with thread_lock:
    # #         #     while time.time() - last_req < 1:
    # #         #         time.sleep(0.1)
    # #         #     last_req = time.time()
    # #         response = requests.post(url, headers=headers, json=data)
    # #         if response.status_code != 200:
    # #             raise Exception(response.text)
    # #         uid = response.json()['inference_job_token']
    # #         return uid
    # #     except Exception as e:
    # #         print(e)
    # #         return None