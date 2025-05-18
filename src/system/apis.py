import json
import os

from src.utils.helpers import TableDict
from src.utils import sql


class APIManager(TableDict):
    def __init__(self, parent):
        super().__init__(parent)
        self.table_name = 'apis'
        self.parent = parent

    def load(self):
        apis = sql.get_results("""
            SELECT
                name,
                client_key,
                api_key AS api_key,
                config,
                provider_plugin
            FROM apis""")
        self.clear()
        for api_name, client_key, api_key, api_config, provider_plugin in apis:
            if api_key.startswith('$'):
                api_key = os.environ.get(api_key[1:], '')
            if client_key.startswith('$'):
                client_key = os.environ.get(client_key[1:], '')

            self[api_name] = {
                'client_key': client_key,
                'api_key': api_key,
                'provider_plugin': provider_plugin,
                'config': json.loads(api_config)
            }