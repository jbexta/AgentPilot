import json
import os
from abc import abstractmethod

from src.utils import sql
from src.utils.helpers import convert_model_json_to_obj


class ProviderManager:
    def __init__(self):
        self.providers = {}

    def load(self):
        from src.system.plugins import get_plugin_class
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
            if provider not in self.providers:
                provider_class = get_plugin_class('Provider', provider)
                if not provider_class:
                    continue
                provider_obj = provider_class(self, api_id=api_id)
                self.providers[provider] = provider_obj
            # api_config = json.loads(api_config)
            # api_config['api_key'] = api_key
            self.providers[provider].insert_model(model_name, alias, model_config, kind, api_id, api_name, api_config, api_key)

    def get_model(self, model_obj):  # provider, model_name):
        model_obj = convert_model_json_to_obj(model_obj)
        model_provider = self.providers.get(model_obj.get('provider'))
        if not model_provider:
            return None
        return model_provider.get_model(model_obj)

    def to_dict(self):
        return self.providers

    async def run_model(self, model_obj, **kwargs):
        model_obj = convert_model_json_to_obj(model_obj)
        provider = self.providers.get(model_obj['provider'])
        return await provider.run_model(model_obj, **kwargs)

    def get_model_parameters(self, model_obj, incl_api_data=True):
        model_obj = convert_model_json_to_obj(model_obj)
        model_provider = self.providers.get(model_obj.get('provider'))
        if not model_provider:
            return {}
        return model_provider.get_model_parameters(model_obj, incl_api_data)

    def get_scalar(self, prompt, single_line=False, num_lines=0, model_obj=None):
        model_obj = convert_model_json_to_obj(model_obj)
        provider = self.providers.get(model_obj['provider'])
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
        model_config = {**json.loads(api_config), **json.loads(model_config)}  # todo
        if api_key != '':
            # model_config['api_key'] = api_key
            model_config['api_key'] = os.environ.get(api_key[1:], 'NA') if api_key.startswith('$') else api_key
        if api_id not in self.api_ids:
            self.api_ids[api_id] = api_name

        model_key = (kind, model_name)
        self.models[model_key] = model_config
        self.model_api_ids[model_key] = api_id
        self.model_aliases[model_key] = alias

    def get_model(self, model_obj):  # kind, model_name):
        kind, model_name = model_obj.get('kind'), model_obj.get('model_name')
        return self.models.get((kind, model_name), {})

    @abstractmethod
    async def run_model(self, model_obj, **kwargs):  # kind, model_name,
        pass

    # def get_api_parameters(self, mode):

    def get_model_parameters(self, model_obj, incl_api_data=True):
        kind, model_name = model_obj.get('kind'), model_obj.get('model_name')
        if kind == 'CHAT':
            accepted_keys = [
                'temperature',
                'top_p',
                'presence_penalty',
                'frequency_penalty',
                'max_tokens',
            ]
            if incl_api_data:
                accepted_keys.extend([
                    'api_key',
                    'api_base',
                    'api_version',
                    'custom_provider',
                ])
        else:
            accepted_keys = []

        model_config = self.models.get((kind, model_name), {})
        cleaned_model_config = {k: v for k, v in model_config.items() if k in accepted_keys}
        return cleaned_model_config

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

