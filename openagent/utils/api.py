from utils import sql

apis = {}


def load_api_keys():
    global apis
    api_table = sql.get_results("SELECT `name`, `client_key`, `priv_key` FROM apis")
    apis = {api[0].lower(): {'client_key': api[1], 'priv_key': api[2]} for api in api_table}

load_api_keys()
