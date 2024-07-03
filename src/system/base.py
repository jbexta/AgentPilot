from src.system.apis import APIManager
from src.system.config import ConfigManager
from src.system.blocks import BlockManager
from src.system.files import FileManager
from src.system.models import ModelManager
from src.system.roles import RoleManager
from src.system.sandboxes import SandboxManager
from src.system.plugins import PluginManager
from src.system.tools import ToolManager
from src.system.vectordbs import VectorDBManager


class SystemManager:
    def __init__(self):
        self.apis = APIManager()
        self.blocks = BlockManager(parent=self)
        self.config = ConfigManager()
        self.files = FileManager()
        self.models = ModelManager()
        self.plugins = PluginManager()
        self.roles = RoleManager()
        self.sandboxes = SandboxManager()
        self.tools = ToolManager(parent=self)
        self.vectordbs = VectorDBManager(parent=self)

        self.load()

    def load(self):
        for manager in self.__dict__.values():
            if hasattr(manager, 'load'):
                manager.load()
