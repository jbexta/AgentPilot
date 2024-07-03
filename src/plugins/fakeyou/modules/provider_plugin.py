import asyncio
import tempfile
import time

from PySide6.QtCore import QRunnable
from PySide6.QtWidgets import QWidget, QMessageBox

from src.gui.config import ConfigExtTree
from src.utils import sql  # , api
import requests
from uuid import uuid4

from src.utils.helpers import display_messagebox

# api_config = api.apis.get('fakeyou', {})
# acc_key = api_config.get('client_key', '')
# priv_key = api_config.get('priv_key', '')

# # Step 1: Retrieve the cookie for authentication
# login_url = "https://api.fakeyou.com/login"
# login_data = {
#     "username_or_email": acc_key,  # Replace with actual variable or value
#     "password": priv_key  # Replace with actual variable or value
# }
#
# response = requests.post(login_url, json=login_data)
# response_json = response.json()
#
# if not response_json.get("success"):
#     raise ValueError("Authentication failed.")
#
# # Extract the cookie as a string
# cookie_match = re.search(r'^\w+.=([^;]+)', response.headers.get("set-cookie", ""))
# if cookie_match:
#     cookie = cookie_match.group(1)
# else:
#     cookie = None

cookie = None

# # rate limit 1 reqper sec
# thread_lock = asyncio.Lock()


class FakeYouProvider:  # ConfigExtTree):
    def __init__(self):  # , parent, *args, **kwargs):
        # super().__init__(
        #     parent=parent,
        #     namespace='plugins.openai.files',
        #     schema=[
        #         {
        #             'text': 'Created on',
        #             'type': str,
        #             'width': 150,
        #         },
        #         {
        #             'text': 'id',
        #             'type': str,
        #             'visible': False,
        #         },
        #         {
        #             'text': 'Filename',
        #             'type': str,
        #             'width': 150,
        #         },
        #         {
        #             'text': 'Size',
        #             'type': str,
        #             'width': 100,
        #         },
        #         {
        #             'text': 'Purpose',
        #             'type': str,
        #             'width': 100,
        #         }
        #     ],
        #     tree_width=500,
        #     # add_item_prompt=('Add new voice', 'Enter a name for the voice:'),
        #     # del_item_prompt=('Delete voice', 'Are you sure you want to delete this voice?'),
        #     # tree_height=400,
        #     # config_widget=self.Page_Settings_OAI_VecStore_Files(parent=self),
        #     # layout_type=QVBoxLayout
        # )
        self.last_req = 0

    # class LoadRunnable(QRunnable):
    #     def __init__(self, parent):
    #         super().__init__()
    #         self.parent = parent
    #         self.page_chat = parent.main.page_chat
    #
    #     def run(self):
    #         # QApplication.setOverrideCursor(Qt.BusyCursor)
    #         try:
    #             all_files = openai.files.list()
    #
    #             rows = []
    #             for file in all_files.data:
    #                 fields = [
    #                     datetime.utcfromtimestamp(int(file.created_at)).strftime('%Y-%m-%d %H:%M:%S'),
    #                     file.id,
    #                     file.filename,
    #                     file.bytes,
    #                     file.purpose,
    #                 ]
    #                 rows.append(fields)
    #             self.parent.fetched_rows_signal.emit(rows)
    #         except Exception as e:
    #             self.page_chat.main.error_occurred.emit(str(e))
    #         # finally:
    #         #     QApplication.setOverrideCursor(Qt.ArrowCursor)

    # def get_selected_item_id(self):
    #     item = self.tree.currentItem()
    #     if not item:
    #         return None
    #     return item.text(1)
    #
    # # def add_item(self):
    # #     with block_pin_mode():
    # #         text, ok = QInputDialog.getText(self, "Enter name", "Enter a name for the vector store:")
    # #
    # #         if not ok:
    # #             return False
    # #
    # #         openai.beta.vector_stores.create(name=text)
    # #     self.load()
    #
    # def delete_item(self):
    #     id = self.get_selected_item_id()
    #     if not id:
    #         return False
    #
    #     retval = display_messagebox(
    #         icon=QMessageBox.Warning,
    #         title="Delete file",
    #         text="Are you sure you want to delete this voice?",
    #         buttons=QMessageBox.Yes | QMessageBox.No,
    #     )
    #     if retval != QMessageBox.Yes:
    #         return False
    #
    #     openai.beta.vector_stores.delete(vector_store_id=id)
    #     self.load()

    def sync(self):
        self.sync_folders()
        self.sync_voices()

    def sync_folders(self):
        url = "https://api.fakeyou.com/category/list/tts"
        headers = {
            "content-type": "application/json",
            # "credentials": "include",
            # "cookie": f"session={cookie}"
        }
        try:
            existing_categories = sql.get_results("SELECT uuid FROM categories WHERE api_id = 1")
            existing_uuids = [x[0] for x in existing_categories]

            # with thread_lock:
            while time.time() - self.last_req < 1:
                time.sleep(0.1)
            last_req = time.time()
            response = requests.get(url, headers=headers)
            if response.status_code != 200:
                raise Exception(response.text)

            categories = response.json()['categories']
            ins_cats = []
            for cat in categories:
                if cat['model_type'] != 'tts':
                    continue

                uid = cat['category_token']
                parent_uuid = cat['maybe_super_category_token'] or ''
                cat_name = cat['name']
                ins_cats.append([
                    '1',
                    f"'{uid}'",
                    f"'{parent_uuid}'",
                    f"'{cat_name}'"
                ])
                if uid in existing_uuids:
                    existing_uuids.remove(uid)

            sql.execute(f"""
                INSERT OR IGNORE INTO categories (
                    api_id, 
                    uuid, 
                    parent_uuid, 
                    name
                ) 
                VALUES {','.join(['(' + ','.join(cat) + ')' for cat in ins_cats])}""")

            if len(existing_uuids) > 0:
                sql.execute(f"""UPDATE categories SET deleted = 1 WHERE api_id = 1 AND uuid IN ("{'","'.join(existing_uuids)}");""")

            sql.execute("""
                WITH RECURSIVE category_path AS (
                    SELECT
                        id,
                        uuid,
                        parent_uuid,
                        name,
                        uuid AS path
                    FROM categories
                    WHERE path = '' -- IS NULL OR path = ''
                        AND uuid != ''  -- dirty patch cos im too high to fix original problem #todo
                    UNION ALL
                    SELECT
                        c.id,
                        c.uuid,
                        c.parent_uuid,
                        c.name,
                        cp.path || '|' || c.uuid AS path
                    FROM categories AS c
                    JOIN category_path AS cp ON cp.uuid = c.parent_uuid
                )
                UPDATE categories
                SET
                    path = (
                        SELECT
                            path
                        FROM category_path
                        WHERE category_path.id = categories.id
                    )
                WHERE EXISTS (SELECT 1 FROM category_path);""")

        # sql.execute("""
        # WITH RECURSIVE category_path AS (
        #     SELECT
        #         id,
        #         uuid,
        #         parent_uuid,
        #         name,
        #         CAST(IFNULL(parent_uuid, '') AS TEXT) AS path
        #     FROM categories
        #     WHERE path IS NULL OR path = ''
        #     UNION ALL
        #     SELECT
        #         c.id,
        #         c.uuid,
        #         c.parent_uuid,
        #         c.name,
        #         CAST(cp.path || '/' || c.parent_uuid AS TEXT) AS path
        #     FROM categories AS c
        #     JOIN category_path AS cp ON cp.uuid = c.parent_uuid
        # )
        # UPDATE categories
        # SET
        #     path = (
        #         SELECT
        #             path
        #         FROM category_path
        #         WHERE category_path.id = categories.id
        #     )
        # WHERE
        #     EXISTS (
        #         SELECT 1
        #         FROM category_path
        #         WHERE category_path.id = categories.id
        #     );""")

        except Exception as e:
            print(e)

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