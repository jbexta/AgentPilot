
from src.system.apis import APIManager
from src.system.config import ConfigManager
from src.system.agents import AgentManager
from src.system.blocks import BlockManager
from src.system.modules import ModuleManager
from src.system.providers import ProviderManager
from src.system.roles import RoleManager
from src.system.environments import EnvironmentManager
from src.system.tools import ToolManager
from src.system.venvs import VenvManager


class SystemManager(dict):
    def __init__(self):
        super().__init__()
        self._main_gui = None
        self._initial_managers = {
            'modules': ModuleManager,  # ManagerController
            'apis': APIManager,  # ManagerController
            'agents': AgentManager,  # WorkflowManagerController
            'blocks': BlockManager,  # WorkflowManagerController
            'tools': ToolManager,  # WorkflowManagerController
            'providers': ProviderManager,  # ProviderModulesController
            'roles': RoleManager,  # ManagerController
            'environments': EnvironmentManager,
            'venvs': VenvManager,
            'config': ConfigManager,
        }
        for name, mgr in self._initial_managers.items():
            setattr(self, name, mgr(system=self))

    def load(self):
        # iterate through the intialized managers
        for name, mgr in self.__dict__.items():
            if name.startswith('_'):
                continue
            mgr.load()

    def __getattr__(self, name):
        return self.get(name, None)

    def initialize_custom_managers(self):
        for attr_name in list(self.keys()):
            if attr_name.startswith('_'):
                continue

        custom_managers = self.modules.get_modules_in_folder(
            folder_name='Managers',
            fetch_keys=('name', 'class',)
        )
        for name, mgr in custom_managers:
            attr_name = name.lower()
            setattr(self, attr_name, mgr(parent=self))
            if hasattr(getattr(self, attr_name), 'load'):
                getattr(self, attr_name).load()

    def load_manager(self, manager_name):
        mgr = getattr(self, manager_name, None)
        if mgr and hasattr(mgr, 'load'):
            mgr.load()

manager = SystemManager()
