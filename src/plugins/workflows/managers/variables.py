import json

from typing_extensions import override

from utils import sql
from utils.helpers import BaseManager


class VariableManager(BaseManager):
    """Global variables, usable as `{{ name }}` in any template. They live
    in their own settings row, because the settings root rewrites
    app_config from its pages' fields."""
    def __init__(self, system):
        super().__init__(system)

    @override
    def load(self):
        self.clear()
        self.update(sql.get_scalar(
            "SELECT value FROM settings WHERE field = 'variables'",
            load_json=True,
        ) or {})

    @override
    def save(self):
        value = json.dumps(dict(self))
        if sql.get_scalar("SELECT id FROM settings WHERE field = 'variables'"):
            sql.execute(
                "UPDATE settings SET value = ? WHERE field = 'variables'",
                (value,))
        else:
            sql.execute(
                "INSERT INTO settings (field, value) VALUES ('variables', ?)",
                (value,))

    def __setitem__(self, key, value):
        super().__setitem__(key, value)
        self.save()
