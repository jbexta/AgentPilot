import json
import os

from typing_extensions import override

from utils.helpers import BaseManager
from utils import sql


class APIManager(BaseManager):
    def __init__(self, system):
        super().__init__(
            system,
            table_name='apis',
        )

    @override
    def load(self):
        apis = sql.get_results("""
            SELECT
                name,
                client_key,
                api_key AS api_key,
                config
            FROM apis""")
        self.clear()
        for api_name, client_key, api_key, api_config in apis:
            if api_key.startswith('$'):
                api_key = os.environ.get(api_key[1:], '')
            if client_key.startswith('$'):
                client_key = os.environ.get(client_key[1:], '')

            self[api_name] = {
                'client_key': client_key,
                'api_key': api_key,
                'config': json.loads(api_config)
            }

    @override
    def delete(self, key, where_field='id'):
        sql.execute("DELETE FROM models WHERE api_id = ?;", (key,))
        super().delete(key, where_field)