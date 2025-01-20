import json
from src.utils import sql, telemetry


class ConfigManager:
    def __init__(self, parent):
        self.dict = {}

    def load(self):
        sys_config = sql.get_scalar("SELECT `value` FROM `settings` WHERE `field` = 'app_config'")
        self.dict = json.loads(sys_config)

        telemetry_on = self.dict.get("system.telemetry", True)
        telemetry.enabled = telemetry_on

    # def to_dict(self):
    #     return self.dict
