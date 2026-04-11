
"""Flow Node Member Module.

This module provides the Node member, a fundamental workflow control element
that serves as a connection point and data routing mechanism within complex
workflows. Nodes enable sophisticated workflow topologies and data flow
management between different workflow components.

Key Features:
- Workflow topology and connection management
- Data routing and flow control
- Input passthrough and data transformation
- Workflow graph structure support
- Connection point for multiple workflow paths
- Flow control and branching logic
- Integration with workflow execution engine
- Dynamic workflow configuration

Nodes provide the foundational building blocks for creating complex
workflow graphs with sophisticated data flow and control logic.
"""

from plugins.workflows.members import Member
from utils.helpers import set_module_type


@set_module_type(module_type='Members')
class Node(Member):
    workflow_insert_mode = 'single'
    allow_condition = False
    OUTPUT = None

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.input_passthrough = True
        self.receivable_function = None

    def load(self):
        pass
