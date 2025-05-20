import json
import os

from typing_extensions import override

from src.utils.helpers import ManagerController
from src.utils import sql


class APIManager(ManagerController):
    def __init__(self, parent):
        super().__init__(parent, load_table='apis')

    @override
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