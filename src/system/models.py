# import json
# import os
#
# from src.system.plugins import get_plugin_class
# from src.utils import sql
#
#
# class ModelManager:
#     def __init__(self):
#         self.providers = {}
#         # self.models = {}
#
#     def load(self):
#
#         # Load providers
#         for provider in self.providers.values():
#             provider.load()
#
#         # self.models = {}
#         model_res = sql.get_results("""
#             SELECT
#                 CASE
#                     WHEN json_extract(a.config, '$.litellm_prefix') != '' THEN
#                         json_extract(a.config, '$.litellm_prefix') || '/' || json_extract(m.config, '$.model_name')
#                     ELSE
#                         json_extract(m.config, '$.model_name')
#                 END AS model_name,
#                 m.config AS model_config,
#                 a.config AS api_config,
#                 a.provider_plugin AS provider,
#                 m.api_id,
#                 COALESCE(a.api_key, '')
#             FROM models m
#             LEFT JOIN apis a
#                 ON m.api_id = a.id""")
#         for model_name, model_config, api_config, provider, api_id, api_key in model_res:
#             if provider not in self.providers:
#                 provider_obj = get_plugin_class('Provider', provider)(self, api_id)
#                 self.providers[provider] = provider_obj
#                 # provider_obj.load()
#
#             self.providers[provider].add_model(model_name, model_config, api_config, api_key)
#
#     def get_model
#     def to_dict(self):
#         return self.models
#
#     def get_llm_parameters(self, model_name):
#         accepted_keys = [
#             'api_key',
#             'api_base',
#             'api_version',
#             'custom_provider',
#             'temperature',
#             'top_p',
#             'presence_penalty',
#             'frequency_penalty',
#             'max_tokens',
#         ]
#         model_config = self.models.get(model_name, {})
#         llm_config = {k: v for k, v in model_config.items() if k in accepted_keys}
#         # if 'temperature' in llm_config:
#         #     llm_config['temperature'] = float(model_config['llm_config'])
#         return llm_config
#
#     def run_model(self, model_name, messages, stream=False, tools=None):
#         model_config = self.models.get(model_name, {})
#         return litellm.get_chat_response(messages, model_obj=(model_config['model'], model_config), stream=stream, tools=tools)