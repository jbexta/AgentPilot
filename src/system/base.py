from src.system.apis import APIManager
from src.system.config import ConfigManager
from src.system.blocks import BlockManager
# from src.system.files import FileManager
from src.system.modules import ModuleManager
from src.system.providers import ProviderManager
from src.system.roles import RoleManager
from src.system.environments import EnvironmentManager
# from src.system.plugins import PluginManager
# from src.system.tasks import TaskManager
from src.system.tools import ToolManager
from src.system.vectordbs import VectorDBManager
from src.system.venvs import VenvManager
from src.system.workspaces import WorkspaceManager


class SystemManager:
    def __init__(self):
        self.manager_classes = {
            'apis': APIManager,
            'blocks': BlockManager,
            'config': ConfigManager,
            'providers': ProviderManager,
            'modules': ModuleManager,
            'roles': RoleManager,
            'environments': EnvironmentManager,
            'tools': ToolManager,
            'vectordbs': VectorDBManager,
            'venvs': VenvManager,
            'workspaces': WorkspaceManager,
            # 'tasks': TaskManager,
        }
        for name, manager in self.manager_classes.items():
            setattr(self, name, manager(parent=self))

        # self.initialize_custom_managers()

        # self.apis = APIManager()
        # self.blocks = BlockManager(parent=self)
        # self.config = ConfigManager()
        # # self.files = FileManager()
        # self.providers = ProviderManager(parent=self)
        # # self.plugins = PluginManager()
        # self.modules = ModuleManager(parent=self)
        # self.roles = RoleManager()
        # self.environments = EnvironmentManager()
        # self.tools = ToolManager(parent=self)
        # self.vectordbs = VectorDBManager(parent=self)
        # self.venvs = VenvManager(parent=self)
        # self.workspaces = WorkspaceManager(parent=self)
        # self.tasks = TaskManager(parent=self)

    def initialize_custom_managers(self):
        for attr_name in list(self.__dict__.keys()):
            if isinstance(getattr(self, attr_name), dict):
                continue
            if attr_name not in self.manager_classes:
                delattr(self, attr_name)

        # from src.system.base import get_manager_definitions
        custom_managers = self.get_manager_definitions()
        for name, mgr in custom_managers.items():
            setattr(self, name, mgr(parent=self))
            if hasattr(getattr(self, name), 'load'):
                getattr(self, name).load()

    def load(self, manager_name='ALL'):
        if manager_name == 'ALL':
            initial_items = list(self.__dict__.values())  # todo dirty
            for mgr in initial_items:  # self.__dict__.values():
                if hasattr(mgr, 'load'):
                    mgr.load()
            for mgr in self.__dict__.values():
                if mgr not in initial_items and hasattr(mgr, 'load'):
                    mgr.load()
        else:
            mgr = getattr(self, manager_name, None)
            if mgr:
                mgr.load()

    def get_manager(self, name):
        return getattr(self, name, None)

    def get_manager_definitions(self):  # todo dedupe
        # get custom managers
        custom_manager_defs = {}
        module_manager = self.modules
        for module_id, module in module_manager.loaded_modules.items():
            folder = module_manager.module_folders[module_id]
            if folder != 'managers':
                continue
            module_classes = module_manager.module_metadatas[module_id].get('classes', {})
            if len(module_classes) == 0:
                continue
            manager_class_name = next(iter(module_classes.keys()))
            manager_name = module_manager.module_names[module_id]
            manager_class = getattr(module, manager_class_name, None)
            if manager_class:
                custom_manager_defs[manager_name] = manager_class  # todo
        return custom_manager_defs

manager = SystemManager()

