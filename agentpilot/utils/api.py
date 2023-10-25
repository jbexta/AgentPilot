import os
import openai
from agentpilot.utils import sql

apis = {}
llm_apis = {}


def load_api_keys():
    global apis
    api_table = sql.get_results("SELECT `name`, `client_key`, `priv_key` FROM apis")
    apis = {api[0].lower(): {'client_key': api[1], 'priv_key': api[2]} for api in api_table}

    if apis['openai']['priv_key'] == '$OPENAI_API_KEY':
        apis['openai']['priv_key'] = os.environ.get("OPENAI_API_KEY", '')
    openai.api_key = apis['openai']['priv_key']


load_api_keys()
