import json
from src.utils import sql
from src.utils.helpers import TableDict


class RoleManager(TableDict):
    def __init__(self, parent):
        super().__init__(parent)
        self.table_name = 'roles'
