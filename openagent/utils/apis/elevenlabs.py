import tempfile
import time

import requests

from utils import sql, api


def sync_elevenlabs():
    sync_categories_elevenlabs()


api_config = api.apis.get('elevenlabs')


def sync_categories_elevenlabs():
    url = "https://api.elevenlabs.io/v1/voices"

    headers = {
        "Accept": "application/json",
        "xi-apis-key": api_config['priv_key']
    }

    try:
        response = requests.get(url, headers=headers)

        existing_characters = sql.get_results("SELECT uuid FROM voices WHERE api_id = 3")
        existing_uuids = [x[0] for x in existing_characters]

        voices = []
        uuid_cats = {}
        # response = requests.get(url, headers=headers)
        for voice in response.json()['voices']:
            disp_name = voice['name'].replace('"', '')
            known_from = ''
            # cat = voice['category']  # .replace("'", "''")  ###########################
            uuid = voice['voice_id']
            uuid_cats[uuid] = voice['category']
            creator = ''
            lang = ''
            verb = 'rapping' if '(rapping)' in disp_name.lower() else ''
            verb = 'singing' if '(singing)' in disp_name.lower() else ''
            voices.append([
                '3',
                disp_name,
                known_from,
                uuid,
                creator.replace('"', ''),
                lang,
                verb
            ])
            if uuid in existing_uuids: existing_uuids.remove(uuid)

        q = f"""
            INSERT OR IGNORE INTO voices (
                api_id, 
                display_name, 
                known_from,
                uuid, 
                creator, 
                lang, 
                verb
            ) VALUES {','.join(['("' + '","'.join(map(str, voice)) + '")' for voice in voices])}"""
        sql.execute(q)

        if len(existing_uuids) > 0:
            sql.execute(f"""UPDATE voices SET deleted = 1 WHERE api_id = 3 AND uuid IN ("{'","'.join(existing_uuids)}");""")

        sql.execute("""
            DELETE FROM character_categories WHERE api_id = 3""")
        q = f"""
            INSERT INTO character_categories (
                api_id,
                character_uuid,
                cat_uuid
            ) VALUES {','.join([f'(3, "{uuid}", "{cat}")' for uuid, cat in uuid_cats.items()])}"""
        sql.execute(q)

    except Exception as e:
        print(e)


def try_download_voice(voice_uuid, text):
    if api_config['priv_key'] == '': return None
    CHUNK_SIZE = 1024
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_uuid}"

    headers = {
        "Accept": "audio/mpeg",
        "Content-Type": "application/json",
        "xi-apis-key": api_config['priv_key']
    }

    data = {
        "text": text,
        "model_id": "eleven_monolingual_v1",
        "optimize_streaming_latency": 0,
        "voice_settings": {
            "stability": 0.5,
            "similarity_boost": 0.5
        }
    }

    failed = False
    try_count = 0
    while True:
        try:
            response = requests.post(url, json=data, headers=headers)
            if response.status_code != 200:
                failed = True
                raise ConnectionError()

            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as temp_file:
                for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                    if chunk:
                        temp_file.write(chunk)
                return temp_file.name

        except Exception as e:
            time.sleep(0.1)
            try_count += 1
            if try_count > 10 or failed:
                print(f"Failed to download {voice_uuid}. " + str(e))
                return None
