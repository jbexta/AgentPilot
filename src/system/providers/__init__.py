# from .base import *
#
# from .litellm import LitellmProvider
# from .elevenlabs import ElevenLabsProvider

import json
import os
from abc import abstractmethod

from typing_extensions import override

from src.utils import sql
from src.utils.helpers import convert_model_json_to_obj, set_module_type, ManagerController


@set_module_type(module_type='Managers')
class ProviderManager(ManagerController):
    def __init__(self, system, **kwargs):
        super().__init__(system, **kwargs)

    @override
    def load(self):
        model_res = sql.get_results("""
            SELECT
                CASE
                    WHEN json_extract(a.config, '$.litellm_prefix') != '' THEN
                        json_extract(a.config, '$.litellm_prefix') || '/' || json_extract(m.config, '$.model_name')
                    ELSE
                        json_extract(m.config, '$.model_name')
                END AS model_name,
                m.name AS alias,
                m.config AS model_config,
                a.config AS api_config,
                a.provider_plugin AS provider,
                m.kind,
                m.api_id,
                a.name AS api_name,
                COALESCE(a.api_key, '')
            FROM models m
            LEFT JOIN apis a 
                ON m.api_id = a.id""")
        for model_name, alias, model_config, api_config, provider, kind, api_id, api_name, api_key in model_res:
            if provider not in self:
                from src.system import manager
                provider_class = manager.modules.get_module_class(
                    module_type='Providers',
                    module_name=provider,
                )
                if not provider_class:
                    continue
                provider_obj = provider_class(self, api_id=api_id)
                self[provider] = provider_obj

            self[provider].insert_model(model_name, alias, model_config, kind, api_id, api_name, api_config, api_key)

            if api_name.lower() == 'openai':
                self[provider].visible_tabs = ['Chat', 'Speech']
            if api_name.lower() == 'elevenlabs':
                pass

    def get_model(self, model_obj):  # provider, model_name):
        model_obj = convert_model_json_to_obj(model_obj)
        model_provider = self.get(model_obj.get('provider'))
        if not model_provider:
            return None
        return model_provider.get_model(model_obj)

    async def run_model(self, model_obj, **kwargs):
        model_obj = convert_model_json_to_obj(model_obj)
        provider = self.get(model_obj['provider'])
        if provider is None:
            raise ValueError(f"Provider '{model_obj['provider']}' not found.")
        rr = await provider.run_model(model_obj, **kwargs)
        return rr

    async def get_structured_output(self, model_obj, **kwargs):
        model_obj = convert_model_json_to_obj(model_obj)
        provider = self.get(model_obj['provider'])
        if provider is None:
            raise ValueError(f"Provider '{model_obj['provider']}' not found.")
        if not hasattr(provider, 'get_structured_output'):
            return None
        return await provider.get_structured_output(model_obj, **kwargs)

    def get_model_parameters(self, model_obj, incl_api_data=True):
        model_obj = convert_model_json_to_obj(model_obj)
        model_provider = self.get(model_obj.get('provider'))
        if not model_provider:
            return {}
        return model_provider.get_model_parameters(model_obj, incl_api_data)

    def get_scalar(self, prompt, single_line=False, num_lines=0, model_obj=None):
        model_obj = convert_model_json_to_obj(model_obj)
        provider = self.get(model_obj['provider'])
        if provider is None:
            raise ValueError(f"Provider '{model_obj['provider']}' not found.")
        if not hasattr(provider, 'get_scalar'):
            return None
        return provider.get_scalar(prompt, single_line, num_lines, model_obj)


class Provider:
    def __init__(self, parent, api_id=None):
        self.parent = parent
        # self.api_id = api_id
        self.models = {}
        self.api_ids = {}
        self.model_api_ids = {}
        self.model_aliases = {}

    def insert_model(self, model_name, alias, model_config, kind, api_id, api_name, api_config, api_key):
        # model_config overrides api_config
        model_config = {**json.loads(api_config), **json.loads(model_config)}
        if api_key != '':
            # model_config['api_key'] = api_key
            model_config['api_key'] = os.environ.get(api_key[1:], 'NA') if api_key.startswith('$') else api_key
        if api_id not in self.api_ids:
            self.api_ids[api_id] = api_name

        model_key = (kind, model_name)
        self.models[model_key] = model_config
        self.model_api_ids[model_key] = api_id
        self.model_aliases[model_key] = alias

    @abstractmethod
    async def run_model(self, model_obj, **kwargs):  # kind, model_name,
        pass

    # def sync_chat(self):
    #     """Implement this method to show sync button for chat models"""
    #     pass

    # class ChatConfig(ConfigFields):
    #     """Implement this method to show custom config tab in chat tab"""
    #     def __init__(self, parent):
    #         super().__init__(parent=parent)
    #         self.schema = []

    # class ChatModelParameters(ConfigFields):
    #     """Implement this method to show custom parameters for chat models"""
    #     def __init__(self, parent):
    #         super().__init__(parent=parent)
    #         self.schema = []

