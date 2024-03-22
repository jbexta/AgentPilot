# import tempfile
# import time
#
# import requests
# from boto3 import Session
# from botocore.exceptions import BotoCoreError, ClientError
# from contextlib import closing
# import os
# import sys
# import subprocess
# from tempfile import gettempdir
#
# from src.utils import sql  # , api
#
#
# class AWS_Polly_TTS(TTS):
#
#     api_config = api.apis.get('polly', {})
#     acc_key = api_config.get('client_key', '')
#
#     def sync():
#         sync_characters_polly()
#
#     def sync_voices():
#         session = Session(aws_access_key_id=acc_key,
#                           aws_secret_access_key=api_config['priv_key'],
#                           region_name='eu-west-2')
#         polly = session.client("polly")
#
#         try:
#             response = polly.describe_voices(Engine='neural')
#
#             existing_characters = sql.get_results("SELECT uuid FROM voices WHERE api_id = 5")
#             removed_uuids = [x[0] for x in existing_characters]
#
#             voices = []
#             for voice in response['Voices']:
#                 uid = voice['Id']
#                 disp_name = voice['Name']
#                 lang = voice['LanguageCode']
#                 voices.append([
#                     '5',
#                     uid,
#                     disp_name,
#                     lang
#                 ])
#                 if uid in removed_uuids: removed_uuids.remove(uid)
#
#             sql.execute(f"""
#                 INSERT INTO voices (
#                     api_id,
#                     uuid,
#                     display_name,
#                     lang
#                 ) VALUES {','.join(['("' + '","'.join(map(str, voice)) + '")' for voice in voices])}
#                 ON CONFLICT(api_id, uuid)
#                 DO UPDATE SET
#                     display_name=excluded.display_name,
#                     lang=excluded.lang""")
#
#             if len(removed_uuids) > 0:
#                 sql.execute(
#                     f"""UPDATE voices SET deleted = 1 WHERE api_id = 5 AND uuid IN ("{'","'.join(removed_uuids)}");""")
#
#         except Exception as e:
#             print(e)
#
#     def try_download_voice(voice_uuid, text):  # #speech_uuid):  #
#         if api_config['priv_key'] == '': return None
#         failed = False
#         try_count = 0
#         try:
#             session = Session(aws_access_key_id=acc_key,
#                               aws_secret_access_key=api_config['priv_key'],
#                               region_name='eu-west-2')
#             polly = session.client("polly")
#
#             response = polly.synthesize_speech(
#                 TextType="ssml",
#                 Text=f"<speak><prosody rate='120%'>{text}</prosody></speak>",
#                 OutputFormat="mp3", VoiceId=voice_uuid, Engine='neural')
#
#             with closing(response["AudioStream"]) as stream:
#                 with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as temp_file:
#                     temp_file.write(stream.read())
#
#             return temp_file.name
#
#         except Exception as e:
#             time.sleep(0.1)
#             try_count += 1
#             if try_count > 10 or failed:
#                 print(f"Failed to download {text}. " + str(e))
#                 raise e
#
#         # session = Session(aws_access_key_id=acc_key,
#         #                   aws_secret_access_key=api_config['priv_key'],
#         #                   region_name='eu-west-2')
#         # polly = session.client("polly")
#         #
#         # failed = False
#         # try_count = 0
#         # while True:
#         #     time.sleep(0.03)
#         #     try:
#         #         response = polly.get_speech_synthesis_task(TaskId=speech_uuid)
#         #         task = response['SynthesisTask']
#         #         status = task['TaskStatus']
#         #         if status == 'failed':
#         #             failed = True
#         #             raise ConnectionError()
#         #         if status != 'completed':
#         #             continue
#         #         path = task['OutputUri']
#         #         format = task['OutputFormat']
#         #         audio_request = requests.get(path)
#         #         with closing(audio_request["AudioStream"]) as stream:
#         #             with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as temp_file:
#         #                 temp_file.write(stream.read())
#         #         with tempfile.NamedTemporaryFile(suffix=f'.{format}', delete=False) as temp_file:
#         #             temp_file.write(audio_request.content)
#         #             return temp_file.name
#         #
#         #     except Exception as e:
#         #         time.sleep(0.1)
#         #         try_count += 1
#         #         if try_count > 10 or failed:
#         #             print(f"Failed to download {speech_uuid}. " + str(e))
#         #             raise e
#
#     # def generate_voice_async(voice_uuid, text):
#     #     try:
#     #         session = Session(aws_access_key_id=acc_key,
#     #                           aws_secret_access_key=api_config['priv_key'],
#     #                           region_name='eu-west-2')
#     #         polly = session.client("polly")
#     #         kwargs = {
#     #             'Engine': 'neural',
#     #             'Text': text,
#     #             'VoiceId': voice_uuid,
#     #             'OutputFormat': 'mp3',
#     #             'OutputS3BucketName': 'mybucket-oa'
#     #         }
#     #         response = polly.start_speech_synthesis_task(**kwargs)
#     #         speech_task = response['SynthesisTask']
#     #         return speech_task['TaskId']
#     #
#     #     except (BotoCoreError, ClientError) as error:
#     #         # The service returned an error, exit gracefully
#     #         print(error)
#     #         return None
