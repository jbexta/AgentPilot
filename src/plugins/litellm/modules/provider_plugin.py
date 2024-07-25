import tempfile
import time

from src.gui.config import ConfigFields
from src.utils import sql
import requests

from src.utils.provider import Provider


class LitellmProvider(Provider):
    def __init__(self, model_tree):
        super().__init__()
        self.model_tree = model_tree
        self.visible_tabs = ['Chat']

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
                    'tooltip': 'When enabled, this will override the temperature for all models under this API',
                    'row_key': 'A',
                    'default': 0.6,
                },
                {
                    'text': 'Presence penalty',
                    'type': float,
                    'has_toggle': True,
                    'label_width': 140,
                    'minimum': -2.0,
                    'maximum': 2.0,
                    'step': 0.2,
                    'row_key': 'A',
                    'default': 0.0,
                },
                {
                    'text': 'Top P',
                    'type': float,
                    'label_width': 150,
                    'has_toggle': True,
                    'minimum': 0.0,
                    'maximum': 1.0,
                    'step': 0.05,
                    'tooltip': 'When enabled, this will override the top P for all models under this API',
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
                    'tooltip': 'When enabled, this will override the max tokens for all models under this API',
                    'default': 100,
                },
                {
                    'text': 'API version',
                    'type': str,
                    'label_width': 140,
                    'width': 118,
                    'has_toggle': True,
                    'row_key': 'D',
                    'tooltip': 'The api version passed to LiteLLM. Usually not needed.',
                    'default': '',
                }
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

    # def sync_all(self):
    #     self.sync_llms()

    def run_model(self, model_name):
        pass
