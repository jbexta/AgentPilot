import asyncio
import json

from PySide6.QtWidgets import QMessageBox
from litellm import acompletion

from src.gui.config import ConfigFields
from src.gui.widgets import find_main_widget
from src.utils.helpers import network_connected, convert_model_json_to_obj, display_messagebox
from src.system.providers import Provider
from src.utils.reset import reset_table


class LitellmProvider(Provider):
    def __init__(self, parent, api_id=None):  # , model_tree):
        super().__init__(parent=parent)
        self.main = find_main_widget(self)
        # self.name = name
        # self.model_tree = model_tree
        # self.api_id = api_id  # un
        self.visible_tabs = ['Chat']

    async def run_model(self, model_obj, **kwargs):
        from src.system.base import manager
        accepted_keys = [
            'temperature',
            'top_p',
            'presence_penalty',
            'frequency_penalty',
            'max_tokens',
            'api_key',
            'api_base',
            'api_version',
            'custom_provider',
        ]
        model_obj = convert_model_json_to_obj(model_obj)
        model_s_params = manager.providers.get_model(model_obj)
        model_obj['model_params'] = {**model_obj.get('model_params', {}), **model_s_params}
        model_obj['model_params'] = {k: v for k, v in model_obj['model_params'].items() if k in accepted_keys}

        print('Model params: ', json.dumps(model_obj['model_params']))

        stream = kwargs.get('stream', True)
        messages = kwargs.get('messages', [])
        tools = kwargs.get('tools', None)

        model_name = model_obj['model_name']
        model_params = model_obj.get('model_params', {})

        # if any msg['content'] == '' or None
        if not all(msg['content'] for msg in messages):
            pass
        # push_messages = messages  # [{'role': msg['role'], 'content': msg['content']} for msg in messages]
        ex = None
        for i in range(5):
            try:
                kwargs = dict(
                    model=model_name,
                    messages=messages,
                    stream=stream,
                    request_timeout=100,
                    **(model_params or {}),
                )
                if tools:
                    kwargs['tools'] = tools
                    kwargs['tool_choice'] = "auto"

                return await acompletion(**kwargs)  # oiawait acompletion(**kwargs)
            except Exception as e:
                if not network_connected():
                    ex = ConnectionError('No network connection.')
                    break
                ex = e
                await asyncio.sleep(0.3 * i)
        raise ex

    async def get_scalar_async(self, prompt, single_line=False, num_lines=0, model_obj=None):
        if single_line:
            num_lines = 1

        if num_lines <= 0:
            response = await self.run_model(model_obj=model_obj, messages=[{'role': 'user', 'content': prompt}], stream=False)
            output = response.choices[0]['message']['content']
        else:
            response_stream = await self.run_model(model_obj=model_obj, messages=[{'role': 'user', 'content': prompt}], stream=True)
            output = ''
            line_count = 0
            async for resp in response_stream:
                if 'delta' in resp.choices[0]:
                    delta = resp.choices[0].get('delta', {})
                    chunk = delta.get('content', '')
                else:
                    chunk = resp.choices[0].get('text', '')

                if chunk is None:
                    continue
                if '\n' in chunk:
                    chunk = chunk.split('\n')[0]
                    output += chunk
                    line_count += 1
                    if line_count >= num_lines:
                        break
                    output += chunk.split('\n')[1]
                else:
                    output += chunk
        return output

    def get_scalar(self, prompt, single_line=False, num_lines=0, model_obj=None):
        loop = asyncio.get_event_loop()
        result = loop.run_until_complete(self.get_scalar_async(prompt, single_line, num_lines, model_obj))
        return result

    class ChatConfig(ConfigFields):
        def __init__(self, parent):
            super().__init__(parent=parent)
            self.label_width = 125
            self.schema = [
                {
                    'text': 'Api Base',
                    'type': str,
                    'label_width': 150,
                    'width': 265,
                    'has_toggle': True,
                    'tooltip': 'The base URL for the API. This will be used for all models under this API',
                    'default': '',
                },
                {
                    'text': 'Litellm prefix',
                    'type': str,
                    'label_width': 150,
                    'width': 118,
                    'has_toggle': True,
                    'tooltip': 'The API provider prefix to be prepended to all model names under this API',
                    'row_key': 'F',
                    'default': '',
                },
                {
                    'text': 'Custom provider',
                    'type': str,
                    'label_width': 140,
                    'width': 118,
                    'has_toggle': True,
                    'tooltip': 'The custom provider for LiteLLM. Usually not needed.',
                    'row_key': 'F',
                    'default': '',
                },
                {
                    'text': 'Temperature',
                    'type': float,
                    'label_width': 150,
                    'has_toggle': True,
                    'minimum': 0.0,
                    'maximum': 1.0,
                    'step': 0.05,
                    'tooltip': 'When enabled, this will be the default temperature for all models under this API',
                    'row_key': 'A',
                    'default': 0.6,
                },
                {
                    'text': 'API version',
                    'type': str,
                    'label_width': 140,
                    'width': 118,
                    'has_toggle': True,
                    'row_key': 'A',
                    'tooltip': 'The api version passed to LiteLLM. Usually not needed.',
                    'default': '',
                },
                {
                    'text': 'Top P',
                    'type': float,
                    'label_width': 150,
                    'has_toggle': True,
                    'minimum': 0.0,
                    'maximum': 1.0,
                    'step': 0.05,
                    'tooltip': 'When enabled, this will be the default `Top P` for all models under this API',
                    'row_key': 'B',
                    'default': 1.0,
                },
                {
                    'text': 'Frequency penalty',
                    'type': float,
                    'has_toggle': True,
                    'label_width': 140,
                    'minimum': -2.0,
                    'maximum': 2.0,
                    'step': 0.2,
                    'row_key': 'B',
                    'default': 0.0,
                },
                {
                    'text': 'Max tokens',
                    'type': int,
                    'has_toggle': True,
                    'label_width': 150,
                    'minimum': 1,
                    'maximum': 999999,
                    'step': 1,
                    'row_key': 'D',
                    'tooltip': 'When enabled, this will be the default `Max tokens` for all models under this API',
                    'default': 100,
                },
                {
                    'text': 'Presence penalty',
                    'type': float,
                    'has_toggle': True,
                    'label_width': 140,
                    'minimum': -2.0,
                    'maximum': 2.0,
                    'step': 0.2,
                    'row_key': 'D',
                    'default': 0.0,
                },
            ]

    class ChatModelParameters(ConfigFields):
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
                    'text': 'Temperature',
                    'type': float,
                    'has_toggle': True,
                    'label_width': 125,
                    'minimum': 0.0,
                    'maximum': 1.0,
                    'step': 0.05,
                    'default': 0.6,
                    'row_key': 'A',
                },
                {
                    'text': 'Presence penalty',
                    'type': float,
                    'has_toggle': True,
                    'label_width': 140,
                    'minimum': -2.0,
                    'maximum': 2.0,
                    'step': 0.2,
                    'default': 0.0,
                    'row_key': 'A',
                },
                {
                    'text': 'Top P',
                    'type': float,
                    'has_toggle': True,
                    'label_width': 125,
                    'minimum': 0.0,
                    'maximum': 1.0,
                    'step': 0.05,
                    'default': 1.0,
                    'row_key': 'B',
                },
                {
                    'text': 'Frequency penalty',
                    'type': float,
                    'has_toggle': True,
                    'label_width': 140,
                    'minimum': -2.0,
                    'maximum': 2.0,
                    'step': 0.2,
                    'default': 0.0,
                    'row_key': 'B',
                },
                {
                    'text': 'Max tokens',
                    'type': int,
                    'has_toggle': True,
                    'label_width': 125,
                    'minimum': 1,
                    'maximum': 999999,
                    'step': 1,
                    'default': 100,
                },
            ]


    # def sync_chat(self):
    #     retval = display_messagebox(
    #         icon=QMessageBox.Warning,
    #         title="Sync voices",
    #         text="Are you sure you want to sync FakeYou voices?",
    #         buttons=QMessageBox.Yes | QMessageBox.No,
    #     )
    #     if retval != QMessageBox.Yes:
    #         return False
    #
    #
    #     reset_table()
    #     try:
    #         # folder_cnt = self.sync_folders()
    #         model_cnt = self.sync_voices()
    #         if hasattr(self, 'model_tree'):
    #             self.model_tree.load()
    #
    #         display_messagebox(
    #             icon=QMessageBox.Information,
    #             title="Success",
    #             text=f"Synced {model_cnt} voices",  # and {folder_cnt} folders."
    #         )
    #     except Exception as e:
    #         display_messagebox(
    #             icon=QMessageBox.Critical,
    #             title="Error syncing voices",
    #             text=f"An error occurred while syncing voices: {e}"
    #         )
    # def sync_all(self):
    #     self.sync_llms()
