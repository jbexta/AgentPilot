import os

import openai
# import agentpilot.operations.src.

from utils import sql
import litellm

apis = {}
llm_apis = {}


def load_api_keys():
    global apis
    api_table = sql.get_results("SELECT `name`, `client_key`, `priv_key` FROM apis")
    apis = {api[0].lower(): {'client_key': api[1], 'priv_key': api[2]} for api in api_table}

    dev_key = os.environ.get("OPENAI_API_KEY", None)
    if dev_key:
        apis['openai']['priv_key'] = dev_key
    openai.api_key = apis['openai']['priv_key']


# def set_llm_api_keys():
#     for api_name, api_config in apis.items():
#         if api_name == 'openai':
#             litellm.openai_key openai.api_key = api_config['priv_key']
#             litellm.openai_key = api_config['priv_key']


load_api_keys()
# set_llm_api_keys()
