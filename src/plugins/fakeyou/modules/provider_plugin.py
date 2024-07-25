import json
import tempfile
import time

from PySide6.QtWidgets import QMessageBox

from src.gui.config import ConfigFields
from src.utils import sql
import requests

from src.utils.helpers import display_messagebox
from src.utils.provider import Provider

cookie = None

# # rate limit 1 reqper sec
# thread_lock = asyncio.Lock()


class FakeYouProvider(Provider):
    def __init__(self, model_tree):
        super().__init__()
        self.model_tree = model_tree
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
                {
                    'text': 'Speed',
                    'type': float,
                    'has_toggle': True,
                    'label_width': 125,
                    'minimum': 0.0,
                    'maximum': 1.0,
                    'step': 0.05,
                    'default': 0.6,
                },
            ]

    def sync_voice(self):
        retval = display_messagebox(
            icon=QMessageBox.Warning,
            title="Sync voices",
            text="Are you sure you want to sync FakeYou voices? This will replace any existing voices.",
            buttons=QMessageBox.Yes | QMessageBox.No,
        )
        if retval != QMessageBox.Yes:
            return False

        try:
            self.sync_folders()
            self.sync_voices()
            self.model_tree.load()
        except Exception as e:
            display_messagebox(
                icon=QMessageBox.Critical,
                title="Error syncing voices",
                text=f"An error occurred while syncing voices: {e}"
            )

    def sync_folders(self):
        url = "https://api.fakeyou.com/category/list/tts"
        headers = {
            "content-type": "application/json",
        }

        sql.execute("DELETE FROM folders WHERE type = 'fakeyou'")

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
            for cat in categories
        ]

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

    def sync_voices(self):
        url = "https://api.fakeyou.com/tts/list"  # dict > models(list of dicts)
        headers = {
            "content-type": "application/json",
            # "credentials": "include",
            # "cookie": f"session={cookie}"
        }
        try:
            existing_characters = sql.get_results(
                """
                SELECT json_extract(config, '$.model_id')
                FROM models
                WHERE api_id=1""",
                return_type='list'
            )
            # existing_characters = sql.get_results("SELECT uuid FROM voices WHERE api_id = 1")
            existing_uuids = [x[0] for x in existing_characters]

            # with thread_lock:
            while time.time() - self.last_req < 1:
                time.sleep(0.1)
            last_req = time.time()
            response = requests.get(url, headers=headers)

            if response.status_code != 200:
                raise Exception(response.text)

            models = response.json()['models']
            voices = []
            uuid_cats = {}
            for voice in models:
                disp_name = voice['title'].replace('"', '')
                uid = voice['model_token']
                uuid_cats[uid] = voice['category_tokens']
                added_on = str(int(time.mktime(time.strptime(voice['created_at'], "%Y-%m-%dT%H:%M:%SZ"))))
                updated_on = str(int(time.mktime(time.strptime(voice['updated_at'], "%Y-%m-%dT%H:%M:%SZ"))))
                pos_count = voice['user_ratings']['positive_count']
                neg_count = voice['user_ratings']['negative_count']
                rating = str(pos_count / (pos_count + neg_count)) if neg_count > 0 else 0.5
                creator = voice['creator_username']
                lang = voice['ietf_primary_language_subtag']
                rapping = '1' if '(rapping)' in disp_name.lower() else '0'
                singing = '1' if '(singing)' in disp_name.lower() else '0'
                voices.append([
                    '1',
                    disp_name,
                    uid,
                    added_on,
                    updated_on,
                    rating,
                    creator,
                    lang,
                    rapping,
                    singing
                ])
                if uid in existing_uuids: existing_uuids.remove(uid)

            sql.execute(f"""
                INSERT OR IGNORE INTO voices (
                    api_id, 
                    display_name, 
                    uuid, 
                    added_on,
                    updated_on,
                    rating, 
                    creator, 
                    lang, 
                    rapping, 
                    singing
                ) VALUES {','.join(['("' + '","'.join(map(str, voice)) + '")' for voice in voices])}""")

            if len(existing_uuids) > 0:
                sql.execute(f"""UPDATE voices SET deleted = 1 WHERE api_id = 1 AND uuid IN ("{'","'.join(existing_uuids)}");""")

            sql.execute("""
                DELETE FROM character_categories WHERE api_id = 1""")
            sql.execute(f"""
                INSERT INTO character_categories (
                    api_id,
                    character_uuid,
                    cat_uuid
                ) VALUES {','.join([f'(1, "{uuid}", "{cat}")' for uuid, cats in uuid_cats.items() for cat in cats])}""")

        except Exception as e:
            print(e)

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