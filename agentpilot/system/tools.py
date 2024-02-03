import json
from agentpilot.utils import sql


class ToolManager:
    def __init__(self):
        self.tools = {}

    def load(self):
        self.tools = sql.get_results("""
            SELECT
                name,
                config
            FROM tools""", return_type='dict')
        for k, v in self.tools.items():
            self.tools[k] = json.loads(v)

    def to_dict(self):
        return self.tools
