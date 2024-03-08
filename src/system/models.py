import json
import os
from src.utils import sql


class ModelManager:
    def __init__(self):
        self.models = {}

    def load(self):
        self.models = {}
        model_res = sql.get_results("""
            SELECT
                CASE
                    WHEN json_extract(a.config, '$.litellm_prefix') != '' THEN
                        json_extract(a.config, '$.litellm_prefix') || '/' || json_extract(m.config, '$.model_name')
                    ELSE
                        json_extract(m.config, '$.model_name')
                END AS model_name,
                m.config,
                a.priv_key
            FROM models m
            LEFT JOIN apis a ON m.api_id = a.id""")
        for model_name, model_config, api_key in model_res:
            if api_key.startswith('$'):
                api_key = os.environ.get(api_key[1:], '')

            model_config = json.loads(model_config)
            if api_key != '':
                model_config['api_key'] = api_key

            self.models[model_name] = model_config

    def to_dict(self):
        return self.models

    def get_llm_parameters(self, model_name):
        accepted_keys = [
            'api_key',
            'api_base',
            'temperature',
            'top_p',
            'presence_penalty',
            'frequency_penalty',
            'max_tokens',
        ]
        model_config = self.models.get(model_name, {})
        llm_config = {k: v for k, v in model_config.items() if k in accepted_keys}
        # if 'temperature' in llm_config:
        #     llm_config['temperature'] = float(model_config['llm_config'])
        return llm_config
