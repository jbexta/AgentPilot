import json
import tempfile
import time

from PySide6.QtWidgets import QMessageBox

from src.gui.config import ConfigFields
from src.utils import sql
import requests

from src.utils.helpers import display_message_box
from src.system.providers import Provider

cookie = None

# # rate limit 1 reqper sec
# thread_lock = asyncio.Lock()


class ElevenLabsProvider(Provider):
    def __init__(self, api_id, model_tree):
        super().__init__()
        self.model_tree = model_tree
        self.api_id = api_id
        self.visible_tabs = ['Voice']
        self.folder_key = 'fakeyou'
        self.last_req = 0

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
            text="Are you sure you want to sync FakeYou voices?",
            buttons=QMessageBox.Yes | QMessageBox.No,
        )
        if retval != QMessageBox.Yes:
            return False

        try:
            # folder_cnt = self.sync_folders()
            model_cnt = self.sync_voices()
            self.model_tree.load()

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

    def sync_folders(self):
        url = "https://api.fakeyou.com/category/list/tts"
        headers = {
            "content-type": "application/json",
        }

        existing_uuids = sql.get_results(
            "SELECT json_extract(config, '$.cat_uid') FROM folders WHERE type = 'fakeyou'",
            return_type='list'
        )
        # sql.execute("DELETE FROM folders WHERE type = 'fakeyou'")

        while time.time() - self.last_req < 1:
            time.sleep(1)
        self.last_req = time.time()

        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            raise Exception(response.text)

        categories = response.json()['categories']
        formatted_cats = [
            {
                'cat_uid': cat['category_token'],
                'parent_uid': cat['maybe_super_category_token'] or '',
                'cat_name': cat['name']
            }
            for cat in categories if cat['category_token'] not in existing_uuids
        ]

        if len(formatted_cats) == 0:
            return 0

        params = [
            ('fakeyou', None, cat['cat_name'], json.dumps(cat))
            for cat in formatted_cats
        ]
        flat_params = tuple([item for sublist in params for item in sublist])
        sql.execute(f"""
            INSERT INTO folders (
                type,
                parent_id,
                name,
                config
            )
            VALUES {', '.join(['(?, ?, ?, ?)' for _ in formatted_cats])}
        """, flat_params)

        # update parents
        sql.execute("""
            UPDATE folders
            SET parent_id = (
                SELECT parent.id
                FROM folders AS parent
                WHERE json_extract(parent.config, '$.cat_uid') = json_extract(folders.config, '$.parent_uid')
                LIMIT 1
            )
            WHERE type = 'fakeyou';
        """)

        return len(formatted_cats)

    def sync_voices(self):
        url = "https://api.fakeyou.com/tts/list"  # dict > models(list of dicts)
        headers = {
            "content-type": "application/json",
            # "credentials": "include",
            # "cookie": f"session={cookie}"
        }

        existing_uids = sql.get_results(
            """
            SELECT json_extract(config, '$.model_id')
            FROM models
            WHERE api_id = ?""",
            (self.api_id,),
            return_type='list'
        )

        while time.time() - self.last_req < 1:
            time.sleep(1)
        self.last_req = time.time()

        response = requests.get(url, headers=headers)

        if response.status_code != 200:
            raise Exception(response.text)

        models = response.json()['models']
        formatted_models = [
            {
                'model_name': model['model_token'],
                'cat_uids': model['category_tokens'],
                'title': model['title'].replace('"', ''),
            }
            for model in models if model['model_token'] not in existing_uids
        ]

        if len(formatted_models) == 0:
            return 0

        params = [
            (self.api_id, model['title'], json.dumps(model))
            for model in formatted_models
        ]
        flat_params = tuple([item for sublist in params for item in sublist])
        sql.execute(f"""
            INSERT INTO models (
                api_id,
                kind,
                name,
                config
            )
            VALUES {', '.join(['(?, "VOICE", ?, ?)' for _ in formatted_models])}
        """, flat_params)

        return len(formatted_models)

    def try_download_voice(self, speech_uuid):
        if not speech_uuid: return None
        url = f"https://api.fakeyou.com/tts/job/{speech_uuid}"
        headers = {
            "content-type": "application/json",
            "credentials": "include",
            "cookie": f"session={cookie}"
        }
        try_count = 0
        while True:
            try:
                # with thread_lock:
                #     while time.time() - last_req < 1:
                #         time.sleep(0.1)
                #     last_req = time.time()
                response = requests.get(url, headers=headers)
                if response.status_code != 200:
                    raise ConnectionError()

                path = response.json()['state']['maybe_public_bucket_wav_audio_path']
                if not path: raise Exception("No path")

                audio_request = requests.get(f'https://storage.googleapis.com/vocodes-public{path}')
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_file:
                    temp_file.write(audio_request.content)
                    return temp_file.name

            except Exception as e:
                time.sleep(0.1)
                try_count += 1
                if try_count > 10:
                    print(f"Failed to download {speech_uuid}")
                    return None


    # def generate_voice_async(voice_uuid, text):
    #     global last_req
    #     url = 'https://api.fakeyou.com/tts/inference'
    #     headers = {
    #         "content-type": "application/json",
    #         "credentials": "include",
    #         "cookie": f"session={cookie}"
    #     }
    #     data = {
    #         'tts_model_token': voice_uuid,
    #         'uuid_idempotency_token': str(uuid4()),
    #         'inference_text': text
    #     }
    #     try:
    #         # with thread_lock:
    #         #     while time.time() - last_req < 1:
    #         #         time.sleep(0.1)
    #         #     last_req = time.time()
    #         response = requests.post(url, headers=headers, json=data)
    #         if response.status_code != 200:
    #             raise Exception(response.text)
    #         uid = response.json()['inference_job_token']
    #         return uid
    #     except Exception as e:
    #         print(e)
    #         return None