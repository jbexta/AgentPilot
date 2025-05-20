
from src.utils.helpers import ManagerWorkflowController


class AgentManager(ManagerWorkflowController):
    def __init__(self, parent):
        super().__init__(parent)
        self.table_name = 'entities'  # todo rename back to agents
        self.parent = parent
        # self.empty_config = {'info.name': name}