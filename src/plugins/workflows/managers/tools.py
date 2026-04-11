"""Tool Manager Module.

This module provides the ToolManager class for managing tools within the Agent Pilot system.
Tools are executable functions that agents can invoke to perform specific tasks, ranging from
simple code execution to complex workflow orchestration. The ToolManager handles tool
registration, parameter schema generation, and execution coordination.

Key Features:
- Tool creation, modification, and deletion with workflow support
- Dynamic parameter schema generation from tool configurations
- Asynchronous tool execution with streaming responses
- UUID-based tool identification and name mapping
- Integration with the workflow execution system
- Support for code blocks and complex workflow tools

Tools can be assigned to agents and invoked during conversations to extend agent capabilities
beyond text generation, enabling interactions with external systems, data processing,
and automated task execution.
"""  # unchecked

import asyncio
import json

from utils import sql
from utils.helpers import receive_workflow, params_to_schema
from utils.helpers import BaseManager


class ToolManager(BaseManager):
    def __init__(self, system):
        super().__init__(
            system,
            table_name='tools',
            load_columns=['uuid', 'config'],
            default_fields={
                'config': {'_TYPE': 'code'}
            },
            config_is_workflow=True,
        )
        self.tool_id_names = {}

    def load(self):
        tools_data = sql.get_results("SELECT name, config FROM tools", return_type='dict')
        self.tool_id_names = sql.get_results("SELECT uuid, name FROM tools", return_type='dict')
        self.clear()
        self.update({name: json.loads(config) for name, config in tools_data.items()})

    def get_param_schema(self, tool_uuid):
        tool_name = self.tool_id_names.get(tool_uuid)
        tool_config = self.get(tool_name)
        tool_params = tool_config.get('params', [])
        return params_to_schema(tool_params)

    async def compute_tool_async(self, tool_uuid, params=None):
        tool_name = self.tool_id_names.get(tool_uuid)
        tool_config = self.get(tool_name)
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
