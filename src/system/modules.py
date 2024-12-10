
import importlib
import json
import sys
from importlib.util import resolve_name

from src.utils import sql
from src.utils.helpers import convert_to_safe_case
import types
import importlib.abc
# import importlib.util


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
            module_id = self.module_manager.get_module_id(parent_folder, module_name)
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

    #     self.original_import = __import__
    #     __builtins__['__import__'] = self.custom_import
    #
    # def custom_import(self, name, globals=None, locals=None, fromlist=(), level=0):
    #     module_manager = globals.get('__module_manager') if globals else None
    #
    #     if module_manager and level > 0:
    #         package = globals.get('__package__', '')
    #         if package.startswith('virtual_modules.'):
    #             try:
    #                 # Resolve the full name of the module
    #                 full_name = resolve_name(name, package, level)
    #
    #                 # Try to import the module
    #                 return importlib.import_module(full_name)
    #             except ImportError:
    #                 # If it fails, fall back to the original import
    #                 pass
    #
    #     # Use the original import for all other cases
    #     return self.original_import(name, globals, locals, fromlist, level)

    def load(self, import_modules=True):
        modules_table = sql.get_results("""
            WITH RECURSIVE folder_path AS (
                SELECT id, name, parent_id, name AS path
                FROM folders
                WHERE parent_id IS NULL
                
                UNION ALL
                
                SELECT f.id, f.name, f.parent_id, fp.path || '~#~#~#~#~' || f.name
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
            folder_path = '.'.join([convert_to_safe_case(folder) for folder in folder_path.split('~#~#~#~#~')])
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

            auto_load = config.get('auto_load', False)
            if module_id not in self.loaded_modules and import_modules and auto_load:
                self.load_module(module_id)

    def get_module_id(self, folder_path, module_name):
        return self.folder_modules.get(folder_path, {}).get(module_name)

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
            # else:
            #     module = sys.modules[full_module_name]

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

    # def load_module(self, module_id):
    #     module_name = self.module_names[module_id]
    #     # module_config = self.modules[module_id]
    #     folder_path = self.module_folders[module_id]
    #
    #     try:
    #         full_module_name = f'virtual_modules.{folder_path}.{module_name}'
    #
    #         if full_module_name not in sys.modules:
    #             # Create parent modules if they don't exist
    #             parts = full_module_name.split('.')
    #             for i in range(1, len(parts)):
    #                 parent_module_name = '.'.join(parts[:i])
    #                 if parent_module_name not in sys.modules:
    #                     parent_module = types.ModuleType(parent_module_name)
    #                     parent_module.__path__ = []
    #                     sys.modules[parent_module_name] = parent_module
    #
    #             # Now import the actual module
    #             module = importlib.import_module(full_module_name)
    #
    #         else:
    #             module = sys.modules[full_module_name]
    #
    #         module.__dict__['__package__'] = f'virtual_modules.{folder}'
    #         self.loaded_modules[module_id] = module
    #         self.loaded_module_hashes[module_id] = self.module_metadatas[module_id].get('hash')
    #
    #         return module
    #     except Exception as e:
    #         print(f"Error importing `{module_name}`: {e}")
    #         return e

    # def load_module(self, module_id):  # , module_data):
    #     module_name = self.module_names[module_id]
    #     module_config = self.modules[module_id]
    #
    #     try:
    #         # if not module_config.get('auto_load', False):  # !420! #
    #         #     raise ValueError(f"Module is not enabled")
    #
    #         module_hash = self.module_metadatas[module_id].get('hash')
    #         rechecked_hash = hash_config(module_config, exclude=['auto_load'])  # hashlib.sha1(json.dumps(module_config).encode()).hexdigest()
    #         if module_hash != rechecked_hash:
    #             raise ValueError(f"Module has been modified externally")
    #         code = module_config['data']
    #
    #         with tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix='.py') as temp_file:
    #             temp_file.write(code)
    #             temp_file_path = temp_file.name
    #
    #         spec = importlib.util.spec_from_file_location(module_name, temp_file_path)
    #         module = importlib.util.module_from_spec(spec)
    #         sys.modules['virt.' + module_name] = module
    #         spec.loader.exec_module(module)
    #
    #         os.unlink(temp_file_path)
    #
    #         module_hash = self.module_metadatas[module_id].get('hash')
    #         self.loaded_modules[module_id] = module
    #         self.loaded_module_hashes[module_id] = module_hash
    #
    #         module.__dict__['__package__'] = f'virtual_modules.{folder}'
    #         return module
    #     except Exception as e:
    #         print(f"Error importing `{module_name}`: {e}")
    #         return e