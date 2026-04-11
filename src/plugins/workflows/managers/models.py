"""
Models Manager Module.
"""  # unchecked

import json
import os

from PySide6.QtWidgets import QMessageBox
from typing_extensions import override

from utils.helpers import BaseManager, convert_model_json_to_obj, display_message
from utils import sql
from gui import system


class ModelsManager(BaseManager):
    def __init__(self, system):
        super().__init__(
            system,
            table_name='models',
        )
        self.model_api_ids = {}
        self.model_aliases = {}
        self.api_ids = {}

    @override
    def load(self):
        model_res = sql.get_results("""
            SELECT
                COALESCE(json_extract(m.config, '$._model_name'), json_extract(m.config, '$.model_name')) AS model_name,
                m.name AS alias,
                m.config AS model_config,
                a.config AS api_config,
                m.provider_plugin AS provider,
                m.kind,
                m.api_id,
                a.name AS api_name,
                COALESCE(a.api_key, '')
            FROM models m
            LEFT JOIN apis a 
                ON m.api_id = a.id""")
        for model_name, alias, model_config, api_config, provider, kind, api_id, api_name, api_key in model_res:
            if provider is None:
                print(f"Skipping model '{model_name}' with no provider.")
                continue

            self.add_model(model_name, provider, alias, model_config, kind, api_id, api_name, api_config, api_key)
    
    def add_model(self, model_name, provider, alias, model_config, kind, api_id, api_name, api_config, api_key):
        # model_config overrides api_config
        model_config = {**json.loads(api_config), **json.loads(model_config)}
        if api_key != '':
            # model_config['api_key'] = api_key
            model_config['api_key'] = os.environ.get(api_key[1:], 'NA') if api_key.startswith('$') else api_key
        if api_id not in self.api_ids:
            self.api_ids[api_id] = api_name

        model_key = (provider, kind, model_name)
        self[model_key] = model_config
        self.model_api_ids[model_key] = api_id
        self.model_aliases[model_key] = alias

    def get_model(self, model_obj):  # provider, kind, model_name):
        provider, kind, model_name = model_obj['provider'], model_obj['kind'], model_obj['_model_name']
        model = self.get((provider, kind, model_name), None)
        if model is None:
            raise ValueError(f"Model '{model_name}' not found.")
            
        return model

    async def run_model(self, model_obj, **kwargs):
        model_obj = convert_model_json_to_obj(model_obj)
        provider = system.manager.providers.get(model_obj['provider'])
        if provider is None:
            raise ValueError(f"Provider '{model_obj['provider']}' not found.")
        rr = await provider.run_model(model_obj, **kwargs)
        return rr

    @override
    def delete(self, key, where_field='id'):
        sql.execute("DELETE FROM models WHERE api_id = ?;", (key,))
        super().delete(key, where_field)
