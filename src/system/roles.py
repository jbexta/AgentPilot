
from src.utils.helpers import ManagerController


class RoleManager(ManagerController):
    def __init__(self, parent):
        super().__init__(parent, load_table='roles')
