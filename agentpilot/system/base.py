from agentpilot.system.config import ConfigManager
from agentpilot.system.blocks import BlockManager
from agentpilot.system.models import ModelManager
from agentpilot.system.roles import RoleManager
from agentpilot.system.sandboxes import SandboxManager
from agentpilot.system.plugins import PluginManager


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
