import json
from src.utils import sql, telemetry
from src.utils.helpers import TableDict


class ConfigManager(TableDict):
    def __init__(self, parent):
        super().__init__(parent)

    def load(self):
        sys_config = sql.get_scalar("SELECT `value` FROM `settings` WHERE `field` = 'app_config'")
        self.clear()
        self.update(json.loads(sys_config))
        # telemetry_on = self.get("system.telemetry", True)
        # telemetry.enabled = telemetry_on

    def save(self):
        sql.execute("UPDATE `settings` SET `value` = ? WHERE `field` = 'app_config'", (json.dumps(dict(self)),))
        self.load()

    def __setitem__(self, key, value):
        super().__setitem__(key, value)
        self.save()

    def __delitem__(self, key):
        super().__delitem__(key)
        self.save()
