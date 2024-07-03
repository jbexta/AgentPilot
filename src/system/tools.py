import json
from src.utils import sql


class ToolManager:
    def __init__(self, parent):
        self.system = parent
        self.tools = {}
        self.tool_id_names = {}  # todo clean
        self.executor = Executor(self)

    def load(self):
        self.tools = sql.get_results("""
            SELECT
                name,
                config
            FROM tools""", return_type='dict')
        for k, v in self.tools.items():
            self.tools[k] = json.loads(v)
        self.tool_id_names = sql.get_results("""
            SELECT
                id,
                name
            FROM tools""", return_type='dict')

    def to_dict(self):
        return self.tools

    def execute(self, tool_name, inputs):
        tool = self.tools.get(tool_name)
        if not tool:
            return None
        return tool.run(inputs)


class Executor:
    def __init__(self, parent):
        self.system = parent.system

    def execute(self, tool_name, inputs):
        return self.tool_manager.execute(tool_name, inputs)