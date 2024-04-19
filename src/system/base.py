from src.system.apis import APIManager
from src.system.config import ConfigManager
from src.system.blocks import BlockManager
from src.system.files import FileManager
from src.system.models import ModelManager
from src.system.roles import RoleManager
from src.system.sandboxes import SandboxManager
from src.system.plugins import PluginManager


class SystemManager:
    def __init__(self):
        self.apis = APIManager()
        self.config = ConfigManager()
        self.blocks = BlockManager()
        self.models = ModelManager()
        self.plugins = PluginManager()
        self.roles = RoleManager()
        self.files = FileManager()
        self.sandboxes = SandboxManager()

        self.load()

    def load(self):
        for manager in self.__dict__.values():
            if hasattr(manager, 'load'):
                manager.load()
