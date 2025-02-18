import inspect
import os

from src.system.apis import APIManager
from src.system.config import ConfigManager
from src.system.blocks import BlockManager
from src.system.modules import ModuleManager
from src.system.providers import ProviderManager
from src.system.roles import RoleManager
from src.system.environments import EnvironmentManager
from src.system.tools import ToolManager
from src.system.vectordbs import VectorDBManager
from src.system.venvs import VenvManager
# from src.system.workspaces import WorkspaceManager


class SystemManager:
    def __init__(self):
        self._main_gui = None
        self._manager_classes = {
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
            # 'workspaces': WorkspaceManager,
        }
        for name, manager in self._manager_classes.items():
            setattr(self, name, manager(parent=self))

    def initialize_custom_managers(self):
        for attr_name in list(self.__dict__.keys()):
            # if isinstance(getattr(self, attr_name), dict):
            #     continue
            if attr_name.startswith('_'):
                continue
            if attr_name not in self._manager_classes:
                delattr(self, attr_name)

        # from src.system.base import get_manager_definitions
        custom_managers = self.get_manager_definitions()
        for name, mgr in custom_managers.items():
            attr_name = name.lower()
            setattr(self, attr_name, mgr(parent=self))
            if hasattr(getattr(self, attr_name), 'load'):
                getattr(self, attr_name).load()

    def load(self, manager_name='ALL'):
        if manager_name == 'ALL':
            initial_items = [v for k, v in self.__dict__.items() if k in self._manager_classes]
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

    def load_manager(self, name):
        mgr = self.get_manager(name)
        if mgr:
            mgr.load()

    def get_manager_definitions(self):  # todo dedupe
        # get custom managers from modules
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

        # get custom managers from src/plugins/addons
        if 'AP_DEV_MODE' in os.environ.keys():  # todo dedupe
            this_file_path = os.path.abspath(__file__)
            project_source_path = os.path.dirname(os.path.dirname(this_file_path))
            addons_path = os.path.join(project_source_path, 'plugins', 'addons')
            addons_names = [name for name in os.listdir(addons_path) if not name.endswith('.py')]
            for addon_name in addons_names:
                managers_path = os.path.join(addons_path, addon_name, 'managers')
                if not os.path.exists(managers_path):
                    continue
                for filename in os.listdir(managers_path):
                    if filename.startswith('_') or not filename.endswith('.py'):
                        continue
                    module_name = filename[:-3]
                    module = __import__(f'plugins.addons.{addon_name}.managers.{module_name}', fromlist=[''])

                    # Find the first class definition in the module
                    for name, obj in inspect.getmembers(module):
                        if inspect.isclass(obj) and obj.__module__ == module.__name__:
                            custom_manager_defs[module_name] = obj
                            break

        return custom_manager_defs

manager = SystemManager()

