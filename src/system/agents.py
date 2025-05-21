
from src.utils.helpers import WorkflowManagerController


class AgentManager(WorkflowManagerController):
    def __init__(self, system):
        super().__init__(system, load_table='entities')  # todo rename back to agents