from src.system.apis import APIManager
from src.system.config import ConfigManager
from src.system.blocks import BlockManager
from src.system.files import FileManager
from src.system.logs import LogManager
from src.system.providers import ProviderManager
# from src.system.models import ModelManager
from src.system.roles import RoleManager
from src.system.sandboxes import SandboxManager
from src.system.plugins import PluginManager
from src.system.tools import ToolManager
from src.system.vectordbs import VectorDBManager
from src.system.venvs import VenvManager
from src.system.workspaces import WorkspaceManager


class SystemManager:
    def __init__(self):
        self.apis = APIManager()
        self.blocks = BlockManager(parent=self)
        self.config = ConfigManager()
        self.files = FileManager()
        self.logs = LogManager(parent=self)
        self.providers = ProviderManager()
        # self.models = ModelManager()
        self.plugins = PluginManager()
        self.roles = RoleManager()
        self.sandboxes = SandboxManager()
        self.tools = ToolManager(parent=self)
        self.vectordbs = VectorDBManager(parent=self)
        self.venvs = VenvManager(parent=self)
        self.workspaces = WorkspaceManager(parent=self)

        self.load()

    def load(self):
        for mgr in self.__dict__.values():
            if hasattr(mgr, 'load'):
                mgr.load()


manager = SystemManager()
