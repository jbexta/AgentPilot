
from src.utils.helpers import WorkflowManagerController


class AgentManager(WorkflowManagerController):
    def __init__(self, parent):
        super().__init__(parent, load_table='entities')  # todo rename back to agents