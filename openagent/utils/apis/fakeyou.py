import asyncio
import re
import tempfile
import time
from openagent.utils import sql
import requests
# from uuid import uuid4
from uuid import uuid4


# # Step 1: Retrieve the cookie for authentication
# login_url = "https://api.fakeyou.com/login"
# login_data = {
#     "username_or_email": 'jbexta',  # Replace with actual variable or value
#     "password": 'J0shu40289'  # Replace with actual variable or value
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

# rate limit 1 reqper sec
last_req = 0
thread_lock = asyncio.Lock()


def sync_fakeyou():
    sync_categories_fakeyou()
    sync_characters_fakeyou()


def sync_categories_fakeyou():
    global last_req
    url = "https://api.fakeyou.com/category/list/tts"
    headers = {
        "content-type": "application/json",
        "credentials": "include",
        "cookie": f"session={cookie}"
    }
    try:
        existing_categories = sql.get_results("SELECT uuid FROM categories WHERE api_id = 1")
        existing_uuids = [x[0] for x in existing_categories]

        with thread_lock:
            while time.time() - last_req < 1:
                time.sleep(0.1)
            last_req = time.time()
            response = requests.get(url, headers=headers)
        if response.status_code != 200:
            raise Exception(response.text)
        categories = response.json()['categories']
        ins_cats = []
        for cat in categories:
            if cat['model_type'] != 'tts': continue

            uid = cat['category_token']
            parent_uuid = cat['maybe_super_category_token']
            if parent_uuid is None: parent_uuid = ''
            cat_name = cat['name']
            ins_cats.append([
                '1',
                f'"{uid}"',
                f'"{parent_uuid}"',
                f'"{cat_name}"'
            ])
            if uid in existing_uuids: existing_uuids.remove(uid)

        sql.execute(f"""
            INSERT OR IGNORE INTO categories (
                api_id, 
                uuid, 
                parent_uuid, 
                name
            ) VALUES {','.join(['(' + ','.join(cat) + ')' for cat in ins_cats])}""")

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


def sync_characters_fakeyou():
    global last_req
    url = "https://api.fakeyou.com/tts/list"  # dict > models(list of dicts)
    headers = {
        "content-type": "application/json",
        "credentials": "include",
        "cookie": f"session={cookie}"
    }
    try:
        existing_characters = sql.get_results("SELECT uuid FROM voices WHERE api_id = 1")
        existing_uuids = [x[0] for x in existing_characters]

        with thread_lock:
            while time.time() - last_req < 1:
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


def try_download_voice(speech_uuid):
    global last_req
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


def generate_voice_async(voice_uuid, text):
    global last_req
    url = 'https://api.fakeyou.com/tts/inference'
    headers = {
        "content-type": "application/json",
        "credentials": "include",
        "cookie": f"session={cookie}"
    }
    data = {
        'tts_model_token': voice_uuid,
        'uuid_idempotency_token': str(uuid4()),
        'inference_text': text
    }
    try:
        # with thread_lock:
        #     while time.time() - last_req < 1:
        #         time.sleep(0.1)
        #     last_req = time.time()
        response = requests.post(url, headers=headers, json=data)
        if response.status_code != 200:
            raise Exception(response.text)
        uid = response.json()['inference_job_token']
        return uid
    except Exception as e:
        print(e)
        return None
