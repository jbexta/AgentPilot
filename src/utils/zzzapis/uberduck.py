import tempfile
import time
from src.utils import sql, api
import requests


def sync_uberduck():
    r = sync_categories_uberduck()
    sync_characters_uberduck(r)


def sync_categories_uberduck():
    url = "https://api.uberduck.ai/voices?mode=tts-all"
    headers = {
        "accept": "application/json",
        "authorization": f"Basic {api.apis['uberduck']['priv_key']}"
    }
    try:
        existing_categories = sql.get_results("SELECT uuid FROM categories WHERE api_id = 2")
        existing_uuids = [x[0] for x in existing_categories]

        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            raise Exception(response.text)

        cats = set()
        for cats_res in response.json():
            cat = cats_res['category'].replace('"', '')
            cats.add(cat)
            if cat in existing_uuids: existing_uuids.remove(cat)

        q = f"""
            INSERT OR IGNORE INTO categories (
                api_id, 
                uuid, 
                parent_uuid, 
                name
            ) VALUES {','.join([f'(2, "{cat}", "", "{cat}")' for cat in cats])}"""
        sql.execute(q)

        if len(existing_uuids) > 0:
            sql.execute(f"""UPDATE categories SET deleted = 1 WHERE api_id = 2 AND uuid IN ("{'","'.join(existing_uuids)}");""")

        return response
    except Exception as e:
        print(e)


def sync_characters_uberduck(response):
    # url = "https://api.uberduck.ai/voices?mode=tts-all"
    # headers = {
    #     "accept": "application/json",
    #     "authorization": f"Basic {api_config['priv_key']}"
    # }
    try:
        existing_characters = sql.get_results("SELECT uuid FROM voices WHERE api_id = 2")
        existing_uuids = [x[0] for x in existing_characters]

        voices = []
        uuid_cats = {}
        # response = requests.get(url, headers=headers)
        for voice in response.json():
            disp_name = voice['display_name'].replace('"', '')
            # cat = voice['category']  # .replace("'", "''")  ###########################
            uuid = voice['voicemodel_uuid']
            uuid_cats[uuid] = voice['category']
            added_on = str(int(voice['added_at'] if voice['added_at'] else 0))
            updated_on = added_on
            rating = '0.5'
            creator = voice['contributors'][0] if voice['contributors'] else ''
            lang = voice['language']
            verb = 'rapping' if '(rapping)' in disp_name.lower() else ''
            verb = 'singing' if '(singing)' in disp_name.lower() else ''
            voices.append([
                '2',
                disp_name,
                uuid,
                added_on,
                updated_on,
                rating,
                creator.replace('"', ''),
                lang,
                verb
            ])
            if uuid in existing_uuids: existing_uuids.remove(uuid)

        q = f"""
            INSERT OR IGNORE INTO voices (
                api_id, 
                display_name, 
                uuid, 
                added_on,
                updated_on,
                rating, 
                creator, 
                lang, 
                verb
            ) VALUES {','.join(['("' + '","'.join(map(str, voice)) + '")' for voice in voices])}"""
        sql.execute(q)

        if len(existing_uuids) > 0:
            sql.execute(f"""UPDATE voices SET deleted = 1 WHERE api_id = 2 AND uuid IN ("{'","'.join(existing_uuids)}");""")

        sql.execute("""
            DELETE FROM character_categories WHERE api_id = 2""")
        q = f"""
            INSERT INTO character_categories (
                api_id,
                character_uuid,
                cat_uuid
            ) VALUES {','.join([f'(2, "{uuid}", "{cat}")' for uuid, cat in uuid_cats.items()])}"""
        sql.execute(q)

    except Exception as e:
        print(e)


def try_download_voice(speech_uuid):
    if api.apis['uberduck']['priv_key'] == '': return None
    if not speech_uuid: return None
    url = f"https://api.uberduck.ai/speak-status?uuid={speech_uuid}"
    headers = {"accept": "application/json"}
    failed = False
    try_count = 0
    while True:
        try:
            response = requests.get(url, headers=headers)
            if response.status_code != 200:
                failed = True
                raise ConnectionError()

            res_json = response.json()
            path = res_json['path']
            failed = res_json['failed_at'] is not None
            if failed: raise Exception('Failed')

            audio_request = requests.get(path)
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_file:
                temp_file.write(audio_request.content)
                return temp_file.name

        except Exception as e:
            time.sleep(0.1)
            try_count += 1
            if try_count > 10 or failed:
                print(f"Failed to download {speech_uuid}. " + str(e))
                return None
            # if failed to generate voice, return none


def generate_voice_async(voice_uuid, text):
    if api.apis['uberduck']['priv_key'] == '': return None

    url = "https://api.uberduck.ai/speak"

    payload = {
        "pace": 1,
        "voicemodel_uuid": voice_uuid,
        "speech": text
    }
    headers = {
        "accept": "application/json",
        "uberduck-id": "anonymous",
        "content-type": "application/json",
        "authorization": f"Basic {api.apis['uberduck']['priv_key']}"
    }
    try:
        response = requests.post(url, json=payload, headers=headers)
        if response.status_code != 200:
            raise Exception(response.text)
        uuid = response.json()['uuid']
        return uuid
    except Exception as e:
        print(e)
        return None


# def generate_voice(voice_uuid, text):
#     url = "https://api.uberduck.ai/speak-synchronous"
#     payload = {
#         "pace": 1,
#         "speech": text,
#         "voicemodel_uuid": voice_uuid
#     }
#     headers = {
#         "accept": "application/json",
#         "uberduck-id": "anonymous",
#         "content-type": "application/json",
#         "authorization": f"Basic {api_config['priv_key']}"
#     }
#
#     response = requests.post(url, json=payload, headers=headers)
#     content = response.content
#
#     with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_file:
#         temp_file.write(content)
#         temp_file.close()
#         return temp_file.name
#         # # play asyncronously
#         # process = subprocess.Popen(['aplay', temp_file.name])
#         # process.communicate()
#         # # os.system(f"aplay {temp_file.name}")
