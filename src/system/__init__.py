
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
            'config': ConfigManager,
            'modules': ModuleManager,
            'apis': APIManager,
            'agents': AgentManager,
            'blocks': BlockManager,
            'tools': ToolManager,
            'providers': ProviderManager,  # ProviderModulesController
            'roles': RoleManager,
            'environments': EnvironmentManager,
            'venvs': VenvManager,
        }
        for name, mgr in self._initial_managers.items():
            setattr(self, name, mgr(system=self))
        # self.modules.load()

    def reload_managers(self):
        custom_managers = self.modules.get_modules_in_folder(
            module_type='Managers',
            fetch_keys=('name', 'class',)
        )
        for name, mgr in custom_managers:
            if mgr:
                setattr(self, name, mgr(self))

    def load(self):
        self.reload_managers()

        for name, mgr in self.__dict__.items():
            if name.startswith('_'):
                continue
            print(f'Loading manager: {name}')
            mgr.load()

    def __getattr__(self, name):
        return self.get(name, None)

    def load_manager(self, manager_name):
        mgr = getattr(self, manager_name, None)
        if mgr:
            mgr.load()

manager = SystemManager()
