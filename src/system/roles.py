
from utils.helpers import ManagerController


class RoleManager(ManagerController):
    def __init__(self, system):
        super().__init__(
            system,
            table_name='roles',
            load_columns=['name', 'config']
        )
