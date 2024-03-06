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
                json_extract(m.config, '$.model_name') as model_name,
                m.config,
                a.priv_key
            FROM models m
            LEFT JOIN apis a ON m.api_id = a.id""")
        for model_name, model_config, priv_key in model_res:
            if priv_key == '$OPENAI_API_KEY':
                priv_key = os.environ.get("OPENAI_API_KEY", '')
            elif priv_key == '$PERPLEXITYAI_API_KEY':
                priv_key = os.environ.get("PERPLEXITYAI_API_KEY", '')

            model_config = json.loads(model_config)
            if priv_key != '':
                model_config['api_key'] = priv_key

            self.models[model_name] = model_config

    def to_dict(self):
        return self.models
