import asyncio
from litellm import acompletion

from src.gui.config import ConfigFields
from src.gui.widgets import find_main_widget
from src.utils.helpers import network_connected, convert_model_json_to_obj
from src.system.providers import Provider


class RoutellmProvider(Provider):
    def __init__(self, parent, api_id=None):  # , model_tree):
        super().__init__(parent=parent)
        self.main = find_main_widget(self)
        # self.name = name
        # self.model_tree = model_tree
        # self.api_id = api_id  # un
        self.visible_tabs = ['Chat']

    async def run_model(self, model_obj, **kwargs):  # kind, model_name, messages, stream=True, tools=None):
        pass
        # # model, model_config = model_obj or ('gpt-3.5-turbo', {})
        # model_obj = convert_model_json_to_obj(model_obj)
        # stream = kwargs.get('stream', True)
        # messages = kwargs.get('messages', [])
        # tools = kwargs.get('tools', None)
        #
        # model_name = model_obj['model_name']
        # model_config = model_obj.get('model_config', {})
        #
        # push_messages = [{'role': msg['role'], 'content': msg['content']} for msg in messages]
        # ex = None
        # for i in range(5):
        #     try:
        #         kwargs = dict(
        #             model=model_name,
        #             messages=push_messages,
        #             stream=stream,
        #             request_timeout=100,
        #             **(model_config or {}),
        #         )
        #         if tools:
        #             kwargs['tools'] = tools
        #             kwargs['tool_choice'] = "auto"
        #
        #         return await acompletion(**kwargs)  # await acompletion(**kwargs)
        #     except Exception as e:
        #         if not network_connected():
        #             ex = ConnectionError('No network connection.')
        #             break
        #         ex = e
        #         await asyncio.sleep(0.3 * i)
        # raise ex

    class ChatModelParameters(ConfigFields):
        def __init__(self, parent):
            super().__init__(parent=parent)
            self.parent = parent
            self.schema = [
                # {
                #     'text': 'Model name',
                #     'type': str,
                #     'label_width': 125,
                #     'width': 265,
                #     'tooltip': 'The name of the model to send to the API',
                #     'default': '',
                # },
                {
                    'text': 'Strong model',
                    'type': 'ModelComboBox',
                    'default': 'gpt-4o',
                },
                {
                    'text': 'Weak model',
                    'type': 'ModelComboBox',
                    'default': 'mistral/mistral-small',
                },
                # {
                #     'text': 'Temperature',
                #     'type': float,
                #     'has_toggle': True,
                #     'label_width': 125,
                #     'minimum': 0.0,
                #     'maximum': 1.0,
                #     'step': 0.05,
                #     'default': 0.6,
                #     'row_key': 'A',
                # },
                # {
                #     'text': 'Presence penalty',
                #     'type': float,
                #     'has_toggle': True,
                #     'label_width': 140,
                #     'minimum': -2.0,
                #     'maximum': 2.0,
                #     'step': 0.2,
                #     'default': 0.0,
                #     'row_key': 'A',
                # },
                # {
                #     'text': 'Top P',
                #     'type': float,
                #     'has_toggle': True,
                #     'label_width': 125,
                #     'minimum': 0.0,
                #     'maximum': 1.0,
                #     'step': 0.05,
                #     'default': 1.0,
                #     'row_key': 'B',
                # },
                # {
                #     'text': 'Frequency penalty',
                #     'type': float,
                #     'has_toggle': True,
                #     'label_width': 140,
                #     'minimum': -2.0,
                #     'maximum': 2.0,
                #     'step': 0.2,
                #     'default': 0.0,
                #     'row_key': 'B',
                # },
                # {
                #     'text': 'Max tokens',
                #     'type': int,
                #     'has_toggle': True,
                #     'label_width': 125,
                #     'minimum': 1,
                #     'maximum': 999999,
                #     'step': 1,
                #     'default': 100,
                # },
            ]

    # def sync_all(self):
    #     self.sync_llms()
