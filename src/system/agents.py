
from src.utils.helpers import ManagerController


class AgentManager(ManagerController):
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
            config_is_workflow=True,
        )  # todo rename back to agents
