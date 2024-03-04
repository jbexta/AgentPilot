import json
from src.utils import sql


class ConfigManager:
    def __init__(self):
        self.dict = {}

    def load(self):
        sys_config = sql.get_scalar("SELECT `value` FROM `settings` WHERE `field` = 'app_config'")
        self.dict = json.loads(sys_config)

    # def to_dict(self):
    #     return self.dict
