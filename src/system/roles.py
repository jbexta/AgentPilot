import json
from src.utils import sql


class RoleManager:
    def __init__(self, parent):
        self.roles = {}

    def load(self):
        self.roles = sql.get_results("""
            SELECT
                name,
                config
            FROM roles""", return_type='dict')
        for k, v in self.roles.items():
            self.roles[k] = json.loads(v)

    def to_dict(self):
        return self.roles

    def get_role_config(self, role_name):
        return self.roles.get(role_name, {})

    def new_role(self, name, config):
        pass

    def delete_role(self, name):
        pass
