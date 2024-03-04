from src.system.config import ConfigManager
from src.system.blocks import BlockManager
from src.system.models import ModelManager
from src.system.roles import RoleManager
from src.system.sandboxes import SandboxManager
from src.system.plugins import PluginManager


class SystemManager:
    def __init__(self):
        self.config = ConfigManager()
        self.blocks = BlockManager()
        self.models = ModelManager()
        self.plugins = PluginManager()
        self.roles = RoleManager()
        self.sandboxes = SandboxManager()

        self.load()

    def load(self):
        self.config.load()
        self.blocks.load()
        self.models.load()
        self.plugins.load()
        self.roles.load()
        self.sandboxes.load()
