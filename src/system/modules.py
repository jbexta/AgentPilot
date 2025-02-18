
import importlib
import inspect
import json
import os
import sys
from importlib.util import resolve_name

from src.utils import sql
from src.utils.helpers import convert_to_safe_case
import types
import importlib.abc


class VirtualModuleLoader(importlib.abc.Loader):
    def __init__(self, module_manager, module_id=None):
        self.module_manager = module_manager
        self.module_id = module_id

    def create_module(self, spec):
        return None

    def exec_module(self, module):
        if self.module_id is not None:
            code = self.module_manager.modules[self.module_id]['data']
            module.__dict__['__module_manager'] = self.module_manager
            exec(code, module.__dict__)
        else:
            # This is a package (folder), so we don't need to execute any code
            module.__path__ = []
            module.__package__ = module.__name__


class VirtualModuleFinder(importlib.abc.MetaPathFinder):
    def __init__(self, module_manager):
        self.module_manager = module_manager

    def find_spec(self, fullname, path, target=None):
        parts = fullname.split('.')
        if parts[0] != 'virtual_modules':
            return None

        if len(parts) > 1:
            folder_path = '.'.join(parts[1:])

            # Check if it's a folder
            if folder_path in self.module_manager.folder_modules:
                loader = VirtualModuleLoader(self.module_manager)
                return importlib.util.spec_from_loader(fullname, loader, is_package=True)

            # Check if it's a module
            parent_folder = '.'.join(parts[1:-1])
            module_name = parts[-1]
            module_id = self.module_manager.folder_modules.get(parent_folder, {}).get(module_name)
            if module_id:
                loader = VirtualModuleLoader(self.module_manager, module_id)
                return importlib.util.spec_from_loader(fullname, loader)

        return None


class ModuleManager:
    def __init__(self, parent):
        self.parent = parent
        self.modules = {}
        self.module_names = {}
        self.module_metadatas = {}
        self.loaded_modules = {}
        self.loaded_module_hashes = {}
        self.module_folders = {}
        self.folder_modules = {}

        self.virtual_modules = types.ModuleType('virtual_modules')
        self.virtual_modules.__path__ = []
        sys.modules['virtual_modules'] = self.virtual_modules
        sys.meta_path.insert(0, VirtualModuleFinder(self))

    def load(self, import_modules=True):
        modules_to_load = []
        modules_table = sql.get_results("""
            WITH RECURSIVE folder_path AS (
                SELECT id, name, parent_id, name AS path
                FROM folders
                WHERE parent_id IS NULL
                
                UNION ALL
                
                SELECT f.id, f.name, f.parent_id, fp.path || '~#@~#$~#£~#&~' || f.name
                FROM folders f
                JOIN folder_path fp ON f.parent_id = fp.id
            )
            SELECT
                m.id,
                m.name,
                m.config,
                m.metadata,
                COALESCE(fp.path, '') AS folder_path
            FROM modules m
            LEFT JOIN folder_path fp ON m.folder_id = fp.id;""")
        for module_id, name, config, metadata, folder_path in modules_table:  # !420! #
            config = json.loads(config)
            self.modules[module_id] = config
            self.module_names[module_id] = name
            self.module_metadatas[module_id] = json.loads(metadata)

            # convert to safe case all names and rejoin with '.'
            folder_path = '.'.join([convert_to_safe_case(folder) for folder in folder_path.split('~#@~#$~#£~#&~')])
            self.module_folders[module_id] = folder_path

            # Ensure all parent folders are created as modules
            parts = folder_path.split('.')
            for i in range(len(parts)):
                parent_folder = '.'.join(['virtual_modules'] + parts[:i+1])
                if parent_folder not in sys.modules:
                    parent_module = types.ModuleType(parent_folder)
                    parent_module.__path__ = []
                    parent_module.__package__ = '.'.join(parent_folder.split('.')[:-1])
                    sys.modules[parent_folder] = parent_module

            if folder_path not in self.folder_modules:
                self.folder_modules[folder_path] = {}
            self.folder_modules[folder_path][name] = module_id

            auto_load = config.get('load_on_startup', False)
            if module_id not in self.loaded_modules and import_modules and auto_load:
                # self.load_module(module_id)
                modules_to_load.append(module_id)

        # do this for now to avoid managing import dependencies
        load_count = 1
        while load_count > 0:
            load_count = 0
            for module_id in modules_to_load:
                res = self.load_module(module_id)
                if isinstance(res, Exception):
                    continue
                load_count += 1
                modules_to_load.remove(module_id)
                # Check if the module is in the "System modules" folder
                if 'managers' in self.module_folders[module_id].split('.'):
                    alias = convert_to_safe_case(self.module_names[module_id])
                    setattr(self.parent, alias, res)

    def load_module(self, module_id):
        module_name = self.module_names[module_id]
        folder_path = self.module_folders[module_id]

        try:
            full_module_name = f'virtual_modules.{folder_path}.{module_name}'

            if full_module_name in sys.modules:
                self.unload_module(module_id)

            # Create parent modules if they don't exist
            parts = full_module_name.split('.')
            for i in range(1, len(parts)):
                parent_module_name = '.'.join(parts[:i])
                if parent_module_name not in sys.modules:
                    spec = importlib.util.find_spec(parent_module_name)
                    if spec is None:
                        raise ImportError(f"Can't find spec for {parent_module_name}")
                    parent_module = importlib.util.module_from_spec(spec)
                    sys.modules[parent_module_name] = parent_module
                    spec.loader.exec_module(parent_module)

            # Now import the actual module
            module = importlib.import_module(full_module_name)

            module.__dict__['__package__'] = f'virtual_modules.{folder_path}'
            self.loaded_modules[module_id] = module
            self.loaded_module_hashes[module_id] = self.module_metadatas[module_id].get('hash')

            return module
        except Exception as e:
            print(f"Error importing `{module_name}`: {e}")
            return e

    def unload_module(self, module_id):
        module = self.loaded_modules.get(module_id)
        if module:
            del sys.modules[module.__name__]
            del self.loaded_modules[module_id]
            del self.loaded_module_hashes[module_id]

    def get_modules_in_folder(self, folder_name, with_ids=False):
        folder_modules = set()
        for module_id, _ in self.loaded_modules.items():
            module_folder = self.module_folders[module_id]
            if module_folder != folder_name:
                continue
            module_name = self.module_names[module_id]
            if with_ids:
                folder_modules.add((module_id, module_name))
            else:
                folder_modules.add(module_name)
        return folder_modules

    def get_page_modules(self, with_ids=False):  # todo clean
        user_pages = self.get_modules_in_folder('pages', with_ids)
        if with_ids:  # todo clean
            dev_pages = set((None, pdk) for pdk in get_page_definitions().keys() if pdk not in [p[1] for p in user_pages])
        else:
            dev_pages = set(pdk for pdk in get_page_definitions().keys() if pdk not in user_pages)

        return user_pages.union(dev_pages)

    def get_manager_modules(self):
        return self.get_modules_in_folder('managers')


def get_page_definitions(with_ids=False):  # include_dev_pages=True):
    from src.system.base import manager
    # get custom pages
    custom_page_defs = {}
    module_manager = manager.modules
    for module_id, module in module_manager.loaded_modules.items():
        folder = module_manager.module_folders[module_id]
        if folder != 'pages':
            continue
        module_classes = module_manager.module_metadatas[module_id].get('classes', {})
        if len(module_classes) == 0:
            continue
        # first class that starts with 'Page'
        page_class_name = next((k for k in module_classes.keys() if k.lower().startswith('page')), None)
        page_name = module_manager.module_names[module_id]
        page_class = getattr(module, page_class_name, None)
        if page_class:
            key = page_name if not with_ids else (module_id, page_name)
            custom_page_defs[key] = page_class

    # get custom pages from src/plugins/addons
    if 'AP_DEV_MODE' in os.environ.keys():  # todo dedupe
        this_file_path = os.path.abspath(__file__)
        project_source_path = os.path.dirname(os.path.dirname(this_file_path))
        addons_path = os.path.join(project_source_path, 'plugins', 'addons')
        addons_names = [name for name in os.listdir(addons_path) if not name.endswith('.py')]
        for addon_name in addons_names:
            managers_path = os.path.join(addons_path, addon_name, 'pages')
            if not os.path.exists(managers_path):
                continue
            for filename in os.listdir(managers_path):
                if filename.startswith('_') or not filename.endswith('.py'):
                    continue
                module_name = filename[:-3]
                module = __import__(f'plugins.addons.{addon_name}.pages.{module_name}', fromlist=[''])

                # Find the first class definition in the module
                for name, obj in inspect.getmembers(module):
                    if inspect.isclass(obj) and obj.__module__ == module.__name__ and name.lower().startswith('page'):
                        key = module_name if not with_ids else (None, module_name)
                        custom_page_defs[key] = obj
                        break

    return custom_page_defs

