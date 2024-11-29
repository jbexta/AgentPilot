import json
from src.utils import sql


class ModuleManager:
    def __init__(self, parent):
        self.parent = parent
        self.modules = {}

    def load(self):
        self.modules = sql.get_results("""
            SELECT
                name,
                config
            FROM modules""", return_type='dict')
        self.modules = {k: json.loads(v) for k, v in self.modules.items()}

    def to_dict(self):
        return self.modules
