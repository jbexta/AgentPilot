import json
from agentpilot.utils import sql


class RoleManager:
    def __init__(self):
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
