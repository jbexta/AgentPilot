
from src.system.apis import APIManager
from src.system.config import ConfigManager
from src.system.agents import AgentManager
from src.system.blocks import BlockManager
from src.system.modules import ModuleManager, PluginManager, get_module_definitions
from src.system.providers import ProviderManager
from src.system.roles import RoleManager
from src.system.environments import EnvironmentManager
from src.system.tools import ToolManager
from src.system.vectordbs import VectorDBManager
from src.system.venvs import VenvManager


class SystemManager:
    def __init__(self):
        self._main_gui = None
        self._manager_classes = {
            'modules': ModuleManager,
            'plugins': PluginManager,
            'apis': APIManager,
            'agents': AgentManager,
            'blocks': BlockManager,
            'config': ConfigManager,
            'providers': ProviderManager,
            'roles': RoleManager,
            'environments': EnvironmentManager,
            'tools': ToolManager,
            'vectordbs': VectorDBManager,
            'venvs': VenvManager,
            # 'workspaces': WorkspaceManager,
        }
        for name, mgr in self._manager_classes.items():
            setattr(self, name, mgr(parent=self))

    def load(self, manager_name='ALL'):
        if manager_name == 'ALL':
            initial_items = [v for k, v in self.__dict__.items() if k in self._manager_classes]
            for mgr in initial_items:
                if hasattr(mgr, 'load'):
                    mgr.load()
            for mgr in self.__dict__.values():
                if mgr not in initial_items and hasattr(mgr, 'load'):
                    mgr.load()
            self.initialize_custom_managers()
        else:
            mgr = getattr(self, manager_name, None)
            if mgr and hasattr(mgr, 'load'):
                mgr.load()

    def initialize_custom_managers(self):
        for attr_name in list(self.__dict__.keys()):
            if attr_name.startswith('_'):
                continue
            if attr_name not in self._manager_classes:
                delattr(self, attr_name)

        custom_managers = get_module_definitions(module_type='managers')
        for name, mgr in custom_managers.items():
            attr_name = name.lower()
            setattr(self, attr_name, mgr(parent=self))
            if hasattr(getattr(self, attr_name), 'load'):
                getattr(self, attr_name).load()

    def get_manager(self, name):
        return getattr(self, name, None)

    def load_manager(self, name):
        mgr = self.get_manager(name)
        if mgr:
            mgr.load()

manager = SystemManager()
