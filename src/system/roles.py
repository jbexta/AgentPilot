
from src.utils.helpers import ManagerController


class RoleManager(ManagerController):
    def __init__(self, system):
        super().__init__(system, load_table='roles')
