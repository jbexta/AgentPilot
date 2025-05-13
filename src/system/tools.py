import asyncio
import json

from src.utils import sql
from src.utils.helpers import receive_workflow, params_to_schema


class ToolManager:
    def __init__(self, parent):
        self.system = parent
        self.tools = {}
        self.tool_id_names = {}

    def load(self):
        tools_data = sql.get_results("SELECT name, config FROM tools", return_type='dict')
        self.tools = {name: json.loads(config) for name, config in tools_data.items()}
        self.tool_id_names = sql.get_results("SELECT uuid, name FROM tools", return_type='dict')

    def to_dict(self):
        return self.tools

    def get_param_schema(self, tool_uuid):
        tool_name = self.tool_id_names.get(tool_uuid)
        tool_config = self.tools.get(tool_name)
        tool_params = tool_config.get('params', [])
        return params_to_schema(tool_params)

    async def compute_tool_async(self, tool_uuid, params=None):
        tool_name = self.tool_id_names.get(tool_uuid)
        tool_config = self.tools.get(tool_name)
        output = ''
        status = 'success'
        async for key, chunk in receive_workflow(tool_config, 'TOOL', params, tool_uuid, main=self.system._main_gui):
            output += chunk
            if key == 'error':
                status = 'error'
        return json.dumps({'output': output, 'status': status, 'tool_uuid': tool_uuid})

    def compute_tool(self, tool_uuid, params=None):  # , visited=None, ):
        # return asyncio.run(self.receive_block(name, add_input))
        return asyncio.run(self.compute_tool_async(tool_uuid, params))
