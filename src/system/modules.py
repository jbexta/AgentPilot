import importlib
import inspect
import json
import pkgutil
import sys
import textwrap
from typing import Dict, Type

from typing_extensions import override

from src.utils import sql
from src.utils.helpers import convert_to_safe_case, get_metadata, get_module_type_folder_id, set_module_type, \
    ManagerController
import types


@set_module_type(module_type="Managers")
class ModuleManager(ManagerController):
    """Manages dynamic loading and unloading of modules."""

    def __init__(self, system):
        super().__init__(system, table_name="modules", load_columns=[
            'uuid', 'type', 'name', 'config', 'metadata', 'locked', 'folder_path'
        ])

        # Initialize type controllers
        self.type_controllers = {
            None: ModulesController(system),
            "managers": ModulesController(system, module_type="managers", load_to_path="src.system"),
            "pages": ModulesController(system, module_type="pages", load_to_path="src.gui.pages"),
            "widgets": ModulesController(system, module_type="widgets", load_to_path="src.gui.widgets"),
            "providers": ModulesController(system, module_type="providers", load_to_path="src.system.providers"),
            "members": ModulesController(system, module_type="members", load_to_path="src.members"),
            "bubbles": ModulesController(system, module_type="bubbles", load_to_path="src.gui.bubbles"),
            "behaviors": ModulesController(system, module_type="behaviors", load_to_path="src.system.behaviors"),
        }

        self.loaded_modules: Dict[int, types.ModuleType] = {}
        self.loaded_module_hashes: Dict[int, str] = {}
        self.plugins: Dict[str, Dict[str, Type]] = {}  # {plugin_type: {name: class}}

    @override
    def load(self):
        for type_controller in self.type_controllers.values():
            type_controller.load()

    def get_module_class(self, module_type, module_name, default=None):
        """Returns the class of a module by its type and module name."""
        type_controller = self.type_controllers.get(module_type.lower())
        if type_controller is None:
            print(f"Module type `{module_type}` not found in type controllers.")
            return default

        folder_type_modules = type_controller.get_modules(fetch_keys=('name', 'class',))
        module_class = next((value for key, value in folder_type_modules if key.lower() == module_name.lower()), default)
        return module_class

    @override
    def add(self, name, **kwargs):
        safe_text = convert_to_safe_case(name).capitalize()
        folder_name = kwargs.pop('folder_name', None)
        config = kwargs.get('config', None)
        if not config:
            if folder_name == 'Pages':
                module_code = f"""
                    from src.gui.util import CVBoxLayout, CHBoxLayout
                    from src.gui.widgets import ConfigDBTree, ConfigFields, ConfigJoined, ConfigDBTree, ConfigJsonTree, ConfigPages, ConfigTabs
            
                    class Page_{safe_text}_Settings(ConfigPages):
                        def __init__(self, parent):
                            super().__init__(parent=parent)
                            # self.icon_path = ":/resources/icon-tasks.png"
                            self.try_add_breadcrumb_widget(root_title=\"\"\"{name}\"\"\")
                            self.pages = {{}}
                """
            elif folder_name == 'Bubbles':
                module_code = f"""
                    from src.gui.bubbles import MessageBubble, MessageButton
                    
                    class Bubble_{safe_text}(MessageBubble):
                        from src.utils.helpers import message_button, message_extension
                    
                        def __init__(self, parent, message):
                            super().__init__(
                                parent=parent,
                                message=message,
                            )
                    
                        def setMarkdownText(self, text):
                            super().setMarkdownText(text)
                """
            else:
                module_code = ''

            config = {
                'load_on_startup': True,
                'source.data': textwrap.dedent(module_code),
            }

        kwargs['metadata'] = json.dumps(get_metadata(config))
        kwargs['folder_id'] = get_module_type_folder_id(module_type=folder_name) if folder_name else None

        super().add(name, **kwargs)

        main = self.system._main_gui
        if main:
            if hasattr(main, 'main_pages'):
                main.main_pages.build_schema()
                # main.page_settings.build_schema()
                main.main_pages.settings_sidebar.toggle_page_pin(name, True)

    @override
    def delete(self, key, where_field='id'):
        self.unload_module(key)
        pages_folder_id = get_module_type_folder_id(module_type='Pages')
        page_name = sql.get_scalar("SELECT name FROM modules WHERE id = ? and folder_id = ?",
                                   (key, pages_folder_id,))
        if page_name and self.system._main_gui:
            self.system._main_gui.main_pages.settings_sidebar.toggle_page_pin(page_name, False)
        super().delete(key, where_field)

    def get_modules_in_folder(self, folder_name=None, fetch_keys=('name',)):
        """Returns a list of modules in the specified folder."""
        if folder_name is None:
            modules = self.type_controllers[None].get_modules(fetch_keys=fetch_keys)
        else:
            folder_name = folder_name.lower()
            if folder_name not in self.type_controllers:
                print(f"Folder `{folder_name}` not found in module types.")  # todo
                return []
            modules = self.type_controllers[folder_name].get_modules(fetch_keys=fetch_keys)

        return modules


class VirtualModuleLoader(importlib.abc.Loader):
    def __init__(self, source_code: str):
        self.source_code = source_code

    def create_module(self, spec):
        return None

    def exec_module(self, module):
        try:
            if self.source_code:
                exec(self.source_code, module.__dict__)
        except SyntaxError as e:
            raise ImportError(f"Invalid source code for {module.__name__}: {e}")


class ModulesController(ManagerController):
    def __init__(
            self,
            system,
            module_type=None,
            load_to_path='src.system.modules',
            **kwargs
    ):
        self.module_type = module_type
        self.load_to_path = load_to_path
        self._loaded_modules = {}  # {name: {'module': module_obj, 'class': class_obj, 'source': 'db'|'file'}}
        self._source_module_names = set()  # Track all available source module names
        super().__init__(system, **kwargs)

    @override
    def load(self):
        """Load all modules, with DB modules taking priority over source modules."""
        # Clear previous state
        old_loaded = self._loaded_modules.copy()
        self._loaded_modules.clear()

        # First, discover all available source module names (without importing)
        self._source_module_names = self._discover_source_modules(self.load_to_path)

        # Load DB modules first (they have priority)
        db_module_names = self._load_db_modules()

        # Load source modules that aren't overridden by DB modules
        self._load_source_modules(skip_names=db_module_names)

        # Clean up old virtual modules from sys.modules
        self._cleanup_old_modules(old_loaded)

    def _discover_source_modules(self, module_path: str, discovered=None):
        """Discover available source module names without importing them."""
        if discovered is None:
            discovered = set()

        try:
            module = importlib.import_module(module_path)
            module_path_iter = pkgutil.iter_modules(module.__path__)
        except (ImportError, AttributeError):
            return discovered

        for _, name, is_pkg in module_path_iter:
            if name == 'base' or name.startswith('_'):
                continue

            if is_pkg:
                # Recursively discover sub-packages
                inner_module_path = f"{module_path}.{name}"
                self._discover_source_modules(inner_module_path, discovered)
            else:
                discovered.add(name)

        return discovered

    def _load_db_modules(self):
        """Load custom modules from database."""
        loaded_names = set()

        rows = sql.get_results(f"""
            WITH RECURSIVE folder_path AS (
                SELECT id, name, parent_id, name AS path
                FROM folders
                WHERE parent_id IS NULL
                UNION ALL
                SELECT f.id, f.name, f.parent_id, fp.path || '.' || f.name
                FROM folders f
                JOIN folder_path fp ON f.parent_id = fp.id
            )
            SELECT
                m.id,
                m.name,
                m.config,
                m.metadata,
                m.locked,
                COALESCE(fp.path, '') AS folder_path
            FROM modules m
            LEFT JOIN folder_path fp ON m.folder_id = fp.id
        """)

        for module_id, name, config, metadata, locked, folder_path in rows:
            if self.module_type and not folder_path.startswith(self.module_type):
                continue

            try:
                # Create virtual module
                module_name = self._get_virtual_module_name(name, folder_path)

                # Ensure parent modules exist
                self._ensure_parent_modules(module_name)

                # Remove old module if exists
                if module_name in sys.modules:
                    del sys.modules[module_name]

                # Create and execute module
                config = json.loads(config)
                source_code = config.get('data', '')
                loader = VirtualModuleLoader(source_code)
                spec = importlib.util.spec_from_loader(module_name, loader)
                module = importlib.util.module_from_spec(spec)
                sys.modules[module_name] = module
                spec.loader.exec_module(module)

                # Extract class
                class_obj = self.extract_module_class(module)
                if class_obj:
                    self._loaded_modules[name] = {
                        'id': module_id,
                        'module': module,
                        'class': class_obj,
                        'source': 'db'
                    }
                    loaded_names.add(name)

            except Exception as e:
                print(f"Error loading database module {name}: {str(e)}")

        return loaded_names

    def _load_source_modules(self, skip_names=None):
        """Load source modules that aren't overridden by DB modules."""
        if skip_names is None:
            skip_names = set()

        self._load_source_modules_recursive(self.load_to_path, skip_names)

    def _load_source_modules_recursive(self, module_path: str, skip_names: set):
        """Recursively load source modules."""
        try:
            module = importlib.import_module(module_path)
            module_path_iter = pkgutil.iter_modules(module.__path__)
        except (ImportError, AttributeError):
            return

        for _, name, is_pkg in module_path_iter:
            if name == 'base' or name.startswith('_'):
                continue

            if is_pkg:
                # Recursively process sub-packages
                inner_module_path = f"{module_path}.{name}"
                self._load_source_modules_recursive(inner_module_path, skip_names)
            else:
                if name in skip_names:
                    continue  # Skip if overridden by DB module

                try:
                    # Import the module
                    full_module_name = f"{module_path}.{name}"
                    module = importlib.import_module(full_module_name)

                    # Force reload to get latest changes
                    importlib.reload(module)

                    class_obj = self.extract_module_class(module)
                    if class_obj:
                        self._loaded_modules[name] = {
                            'id': None,
                            'module': module,
                            'class': class_obj,
                            'source': 'file'
                        }
                except Exception as e:
                    print(f"Error loading source module {name}: {str(e)}")

    def _get_virtual_module_name(self, name, folder_path):
        """Generate virtual module name."""
        module_name = f"virtual_modules.{self.module_type or 'modules'}.{convert_to_safe_case(name)}"

        if folder_path:
            folder_path_safe = ".".join(convert_to_safe_case(folder) for folder in folder_path.split("."))
            module_name = f"virtual_modules.{folder_path_safe}.{convert_to_safe_case(name)}"

        return module_name

    def _ensure_parent_modules(self, module_name):
        """Ensure parent modules exist in sys.modules."""
        parts = module_name.split(".")
        for i in range(1, len(parts)):
            parent_path = ".".join(parts[:i])
            if parent_path not in sys.modules:
                parent_module = types.ModuleType(parent_path)
                parent_module.__path__ = []
                parent_module.__package__ = ".".join(parts[:i - 1]) or ""
                sys.modules[parent_path] = parent_module

    def _cleanup_old_modules(self, old_loaded):
        """Remove virtual modules that are no longer loaded."""
        for name, old_info in old_loaded.items():
            if name not in self._loaded_modules and old_info['source'] == 'db':
                # Remove virtual module from sys.modules
                module = old_info.get('module')
                if module and hasattr(module, '__name__'):
                    module_name = module.__name__
                    if module_name in sys.modules:
                        del sys.modules[module_name]

    def get_modules(self, fetch_keys=('name',)):
        """
        Returns module information based on loaded modules.

        Args:
            fetch_keys: Tuple of keys to include in the result.

        Returns:
            List of tuples containing module data for the specified fetch_keys.
        """
        type_modules = []

        for name, info in self._loaded_modules.items():
            module_item = {
                'id': info['id'],
                'name': name,
                'type': self.module_type,
                'class': info['class'],
            }

            # Filter by fetch_keys
            if fetch_keys:
                module_item = {k: v for k, v in module_item.items() if k in fetch_keys}
            if not module_item:
                continue

            module_values = tuple(module_item.values())
            type_modules.append(module_values)

        # Sort to ensure consistent ordering
        type_modules.sort(key=lambda x: x[fetch_keys.index('name')] if 'name' in fetch_keys else x[0])

        if len(fetch_keys) == 1:
            type_modules = [item[0] for item in type_modules]

        return type_modules

    def extract_module_class(self, module, default=None):
        """Extract the class from a module that matches the module_type."""
        if not module:
            return default

        # Get all module classes defined ONLY in the module
        all_module_classes = [
            (name, obj) for name, obj in inspect.getmembers(module, inspect.isclass)
            if getattr(obj, '__module__', '').startswith(module.__name__)
        ]

        marked_module_classes = [
            (name, obj) for name, obj in all_module_classes
            if getattr(obj, '_ap_module_type', '') == self.module_type
        ]

        if len(all_module_classes) == 1:
            return all_module_classes[0][1]

        if not marked_module_classes:
            print(f"Module `{module.__name__}` has no classes marked as `{self.module_type}`.")
            return default

        if len(marked_module_classes) > 1:
            print(f"Module `{module.__name__}` has multiple classes marked as `{self.module_type}`.")
            return default

        return marked_module_classes[0][1]

# class ModulesController(ManagerController):
#     def __init__(
#             self,
#             system,
#             module_type=None,
#             load_to_path='src.system.modules',
#             **kwargs
#     ):
#         self.module_type = module_type
#         self.load_to_path = load_to_path
#         super().__init__(system, **kwargs)
#
#     @override
#     def load(self):
#         pass
#
#     @override
#     def add(self, name, **kwargs):
#         pass
#
#     @override
#     def delete(self, key, where_field='id'):
#         pass
#
#     def get_modules(self, fetch_keys=('name',)):
#         """
#         Returns a list of modules combining source code modules from load_to_path
#         and custom modules from the database.
#
#         Args:
#             fetch_keys: Tuple of keys to include in the result (e.g., ('name', 'class')).
#
#         Returns:
#             List of tuples containing module data for the specified fetch_keys.
#         """
#         # Get all modules in type
#         source_modules = self.process_module(self.load_to_path, fetch_keys)
#         db_modules = self.process_db_modules(fetch_keys)
#         all_modules = source_modules + db_modules
#         if len(fetch_keys) == 1:
#             all_modules = [item[0] for item in all_modules]
#
#         return all_modules
#
#     def process_module(self, module_path: str, fetch_keys=('name',)):
#         """
#         Process modules from source code at the given module path.
#
#         Args:
#             module_path: Path to scan for modules (e.g., 'src.system.providers').
#             fetch_keys: Keys to include in the result.
#
#         Returns:
#             List of tuples containing module data.
#         """
#         type_modules = []
#         try:
#             # Ensure the module path is valid
#             module = importlib.import_module(module_path)
#             module_path_iter = pkgutil.iter_modules(module.__path__)
#         except (ImportError, AttributeError):
#             return type_modules
#
#         for _, name, is_pkg in module_path_iter:
#             if name == 'base':
#                 continue
#             if name.startswith('_'):
#                 continue
#             try:
#                 if is_pkg:
#                     # Recursively process sub-packages
#                     inner_module_path = f"{module_path}.{name}"
#                     type_modules.extend(self.process_module(inner_module_path, fetch_keys))
#                 else:
#                     # Import the module
#                     module = importlib.import_module(f"{module_path}.{name}")
#                     class_obj = self.extract_module_class(module)
#                     if not class_obj:
#                         continue
#
#                     module_item = {
#                         'id': None,  # Source modules don't have a DB ID
#                         'name': name,
#                         'type': self.module_type,
#                         'class': class_obj,
#                     }
#
#                     # Filter by fetch_keys
#                     if fetch_keys:
#                         module_item = {k: v for k, v in module_item.items() if k in fetch_keys}
#                     if not module_item:
#                         continue
#                     module_values = tuple(
#                         module_item.values())  # if isinstance(module_item, dict) else (module_item,)
#                     type_modules.append(module_values)
#             except Exception as e:
#                 print(f"Error loading source module {name}: {str(e)}")
#
#         return type_modules
#
#     def process_db_modules(self, fetch_keys=('name',)):
#         """
#         Process custom modules stored in the database.
#
#         Args:
#             fetch_keys: Keys to include in the result.
#
#         Returns:
#             List of tuples containing module data.
#         """
#         type_modules = []
#         # Query the database for modules of this type
#         rows = sql.get_results(f"""
#             WITH RECURSIVE folder_path AS (
#                 SELECT id, name, parent_id, name AS path
#                 FROM folders
#                 WHERE parent_id IS NULL
#                 UNION ALL
#                 SELECT f.id, f.name, f.parent_id, fp.path || '.' || f.name
#                 FROM folders f
#                 JOIN folder_path fp ON f.parent_id = fp.id
#             )
#             SELECT
#                 m.id,
#                 m.name,
#                 m.config,
#                 m.metadata,
#                 m.locked,
#                 COALESCE(fp.path, '') AS folder_path
#             FROM modules m
#             LEFT JOIN folder_path fp ON m.folder_id = fp.id
#         """)
#         for module_id, name, config, metadata, locked, folder_path in rows:
#             if self.module_type:
#                 if not folder_path.startswith(self.module_type):
#                     continue
#             try:
#                 # Create a virtual module
#                 module_name = f"virtual_modules.{self.module_type or 'modules'}.{convert_to_safe_case(name)}"
#
#                 if folder_path:
#                     folder_path_safe = ".".join(convert_to_safe_case(folder) for folder in folder_path.split("."))
#                     module_name = f"virtual_modules.{folder_path_safe}.{convert_to_safe_case(name)}"
#
#                 # Ensure parent modules exist
#                 parent_path = ".".join(module_name.split(".")[:-1])
#                 if parent_path and parent_path not in sys.modules:
#                     parent_module = types.ModuleType(parent_path)
#                     parent_module.__path__ = []
#                     parent_module.__package__ = ".".join(parent_path.split(".")[:-1]) or ""
#                     sys.modules[parent_path] = parent_module
#
#                 # Clear existing module from sys.modules
#                 if module_name in sys.modules:
#                     print(f"Removing stale module {module_name} from sys.modules")
#                     del sys.modules[module_name]
#
#                 # Create and execute the module
#                 config = json.loads(config)
#                 source_code = config.get('data', '')
#                 loader = VirtualModuleLoader(source_code)
#                 spec = importlib.util.spec_from_loader(module_name, loader)
#                 module = importlib.util.module_from_spec(spec)
#                 sys.modules[module_name] = module
#                 spec.loader.exec_module(module)
#
#                 # Extract the class
#                 class_obj = self.extract_module_class(module)
#                 if not class_obj:
#                     continue
#
#                 module_item = {
#                     'id': module_id,
#                     'name': name,
#                     'type': self.module_type,
#                     'class': class_obj,
#                 }
#
#                 # Filter by fetch_keys
#                 if fetch_keys:
#                     module_item = {k: v for k, v in module_item.items() if k in fetch_keys}
#                 if not module_item:
#                     continue
#                 module_values = tuple(module_item.values()) if isinstance(module_item, dict) else (module_item,)
#                 type_modules.append(module_values)
#             except Exception as e:  # todo exceptions
#                 print(f"Error loading database module {name}: {str(e)}")
#
#         return type_modules
#
#     def extract_module_class(self, module, default=None):
#         """
#         Extract the class from a module that matches the module_type.
#
#         Args:
#             module: The module object to inspect.
#             default: Default value to return if no class is found.
#
#         Returns:
#             The class object or default.
#         """
#         if not module:
#             return default
#         # all module classes defined ONLY in the module
#         all_module_classes = [
#             (name, obj) for name, obj in inspect.getmembers(module, inspect.isclass)
#             if getattr(obj, '__module__', '').startswith(module.__name__)
#         ]
#         marked_module_classes = [
#             (name, obj) for name, obj in all_module_classes
#             if getattr(obj, '_ap_module_type', '') == self.module_type
#         ]
#         if len(all_module_classes) == 1:
#             return all_module_classes[0][1]
#         if not marked_module_classes:
#             print(f"Module `{module.__name__}` has no classes marked as `{self.module_type}`.")
#             return default
#         if len(marked_module_classes) > 1:
#             print(f"Module `{module.__name__}` has multiple classes marked as `{self.module_type}`.")
#             return default
#         return marked_module_classes[0][1]
#
#     # class ProviderModulesController(ModulesController):
#     #     def __init__(self, system, **kwargs):
#     #         super().__init__(
#     #             system,
#     #             module_type='providers',
#     #             load_to_path='src.system.providers',
#     #             **kwargs
#     #         )
#
#     # class BehaviorModulesController(ModulesController):
#     #     def __init__(self, system, **kwargs):
#     #         super().__init__(
#     #             system,
#     #             module_type='behaviors',
#     #             load_to_path='src.system.behaviors',
#     #             **kwargs
#     #         )
#
#     # class ManagerModulesController(ModulesController):
#     #     def __init__(self, system, **kwargs):
#     #         super().__init__(
#     #             system,
#     #             module_type='managers',
#     #             load_to_path='src.system',
#     #             **kwargs
#     #         )
#
#     # class PageModulesController(ModulesController):
#     #     def __init__(self, system, **kwargs):
#     #         super().__init__(
#     #             system,
#     #             module_type='pages',
#     #             load_to_path='src.gui.pages',
#     #             **kwargs
#     #         )
#
#     # class BubbleModulesController(ModulesController):
#     #     def __init__(self, system, **kwargs):
#     #         super().__init__(
#     #             system,
#     #             module_type='bubbles',
#     #             load_to_path='src.gui.bubbles',
#     #             **kwargs
#     #         )
#
#     # class MemberModulesController(ModulesController):
#     #     def __init__(self, system, **kwargs):
#     #         super().__init__(
#     #             system,
#     #             module_type='members',
#     #             load_to_path='src.members',
#     #             **kwargs
#     #         )
#
#     # class WidgetModulesController(ModulesController):
#     #     def __init__(self, system, **kwargs):
#     #         super().__init__(
#     #             system,
#     #             module_type='widgets',
#     #             load_to_path='src.gui.widgets',
#     #             **kwargs
#     #         )


    # @override
    # def load(self, import_modules: bool = True) -> None:
    #     """Load modules from the database and import those marked for auto-loading."""
    #     # Track modules to unload (those no longer in the database)
    #     modules_to_unload = set(self.loaded_modules.keys())
    #     modules_to_load = []
    #
    #     # Fetch module data from the database
    #     modules_table = sql.get_results("""
    #         WITH RECURSIVE folder_path AS (
    #             SELECT id, name, parent_id, name AS path
    #             FROM folders
    #             WHERE parent_id IS NULL
    #             UNION ALL
    #             SELECT f.id, f.name, f.parent_id, fp.path || '.' || f.name
    #             FROM folders f
    #             JOIN folder_path fp ON f.parent_id = fp.id
    #         )
    #         SELECT
    #             m.id,
    #             NULL,
    #             m.name,
    #             m.config,
    #             m.metadata,
    #             m.locked,
    #             COALESCE(fp.path, '') AS folder_path
    #         FROM modules m
    #         LEFT JOIN folder_path fp ON m.folder_id = fp.id;
    #     """)
    #
    #     # Process module data
    #     for row_tuple in modules_table:
    #         if len(row_tuple) != len(self.load_columns):
    #             raise ValueError(f"Row length {len(row_tuple)} does not match expected columns {len(self.load_columns)}.")
    #
    #         module_id, module_type, name, config, metadata, locked, folder_path = row_tuple
    #         config = json.loads(config)
    #         metadata = json.loads(metadata)
    #         folder_path = ".".join(
    #             convert_to_safe_case(folder) for folder in folder_path.split(".") if folder)
    #         module_type = folder_path.split(".")[0] if folder_path else None
    #         if module_type not in self.type_controllers:
    #             module_type = None
    #
    #         row_tuple = (module_id, module_type, name, config, metadata, locked, folder_path)
    #         self[module_id] = row_tuple
    #
    #         # Determine if module should be loaded
    #         auto_load = config.get("load_on_startup", False)
    #         if import_modules and auto_load and not locked and module_id not in self.loaded_modules:
    #             modules_to_load.append(module_id)
    #         if module_id in modules_to_unload:
    #             modules_to_unload.remove(module_id)
    #
    #     # Load modules, retrying to handle dependencies
    #     while modules_to_load:
    #         failed = []
    #         for module_id in modules_to_load:
    #             try:
    #                 self.load_module(module_id)
    #             except Exception as e:
    #                 failed.append(module_id)
    #         # If no progress is made, avoid infinite loop
    #         if len(failed) == len(modules_to_load):
    #             print(f"Failed to load modules: {[self[mid][2] for mid in failed]}")
    #             break
    #         modules_to_load = failed
    #
    #     # Unload modules no longer needed
    #     for module_id in modules_to_unload:
    #         self.unload_module(module_id)
    #
    # def load_module(self, module_id: int) -> types.ModuleType:
    #     """Load a single module by ID."""
    #     pass
    # #     module_name = self.get_cell(module_id, 'name')
    # #     folder_path = self.get_cell(module_id, 'folder_path')
    # #     module_type = self.get_cell(module_id, 'type')
    # #
    # #     # Determine the import path
    # #     type_controller = self.type_controllers.get(module_type)
    # #     base_path = type_controller.load_to_path if type_controller is not None else None
    # #
    # #     if base_path is None:
    # #         base_path = f'src.system.virtual_modules.{folder_path}'
    # #     else:
    # #         # Keep module_type only if it's the last element in the path
    # #         path_parts = folder_path.split('.')
    # #         if path_parts[-1] == module_type:
    # #             path_parts = path_parts[:-1]
    # #         folder_path = '.'.join(path_parts)
    # #         if folder_path != '':
    # #             base_path = f'{base_path}.{folder_path}'
    # #
    # #     full_module_name = f"{base_path}.{module_name}"
    # #
    # #     try:
    # #         # Ensure parent modules exist
    # #         parent_path = ".".join(full_module_name.split(".")[:-1])
    # #         if parent_path and parent_path not in sys.modules:
    # #             parent_module = types.ModuleType(parent_path)
    # #             parent_module.__path__ = []
    # #             parent_module.__package__ = ".".join(parent_path.split(".")[:-1]) or ""
    # #             sys.modules[parent_path] = parent_module
    # #
    # #         # Import the module
    # #         module = importlib.import_module(full_module_name)
    # #         module.__package__ = parent_path
    # #         self.loaded_modules[module_id] = module
    # #         self.loaded_module_hashes[module_id] = self.get_cell(module_id, 'metadata')  # module_metadatas[module_id].get("hash", "")
    # #
    # #         # Register plugin if applicable
    # #         module_class = self.extract_module_class(module, module_type)
    # #         if module_class and hasattr(module_class, "_ap_plugin_type"):
    # #             plugin_type = module_class._ap_plugin_type
    # #             self.plugins.setdefault(plugin_type, {})[module_name] = module_class
    # #
    # #         return module
    # #
    # #     except ImportError as e:
    # #         print(f"Error importing `{module_name}` at `{full_module_name}`: {e}")
    # #         raise
    #
    # def unload_module(self, module_id):
    #     module = self.loaded_modules.get(module_id)
    #     if module:
    #         try:
    #             del sys.modules[module.__name__]
    #         except KeyError:
    #             pass
    #         del self.loaded_modules[module_id]
    #         del self.loaded_module_hashes[module_id]