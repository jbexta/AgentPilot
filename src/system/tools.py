import asyncio
import json

from src.utils import sql
from src.utils.helpers import receive_workflow


class ToolManager:
    def __init__(self, parent):
        self.system = parent
        self.tools = {}
        self.tool_id_names = {}  # todo clean

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
        type_convs = {
            'String': str,
            'Bool': bool,
            'Int': int,
            'Float': float,
        }
        type_defaults = {
            'String': '',
            'Bool': False,
            'Int': 0,
            'Float': 0.0,
        }

        schema = [
            {
                'key': param.get('name', ''),
                'text': param.get('name', '').capitalize().replace('_', ' '),
                'type': type_convs.get(param.get('type'), str),
                'default': param.get('default', type_defaults.get(param.get('type'), '')),
                'minimum': 99999,
                'maximum': -99999,
                'step': 1,
            }
            for param in tool_params
        ]
        return schema

    async def compute_tool_async(self, tool_uuid, params=None):
        tool_name = self.tool_id_names.get(tool_uuid)
        tool_config = self.tools.get(tool_name)
        chunks = []
        async for key, chunk in receive_workflow(tool_config, 'TOOL', params, tool_uuid):
            chunks.append(chunk)
        return ''.join(chunks)

    def compute_tool(self, tool_uuid, params=None):  # , visited=None, ):
        # return asyncio.run(self.receive_block(name, add_input))
        return asyncio.run(self.compute_tool_async(tool_uuid, params))
