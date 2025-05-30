
from src.utils.helpers import WorkflowManagerController


class AgentManager(WorkflowManagerController):
    def __init__(self, system):
        super().__init__(
            system,
            table_name='entities',
            folder_key='agents',
            load_columns=['uuid', 'config'],
            default_fields={
                'kind': 'AGENT',
            },
            add_item_options={'title': 'Add Agent', 'prompt': 'Enter a name for the agent:'},
            del_item_options={'title': 'Delete Agent', 'prompt': 'Are you sure you want to delete this agent?'},
        )  # todo rename back to agents
