
# import importlib
# import inspect
import json
# import pkgutil
import sys
import textwrap
# from importlib.util import resolve_name
from typing import Dict, Type

from typing_extensions import override

from src.utils import sql
from src.utils.helpers import convert_to_safe_case, get_metadata, get_module_type_folder_id, set_module_type, \
    ManagerController, ProviderModulesController, ManagerModulesController, BubbleModulesController, \
    WidgetModulesController, MemberModulesController, ModulesController, BehaviorModulesController, \
    PageModulesController
import types
# import importlib.abc


# class VirtualModuleLoader(importlib.abc.Loader):
#     def __init__(self):
#         self.source_code = None
#
#     def create_module(self, spec):
#         return None
#
#     def exec_module(self, module):
#         if self.source_code:
#             exec(self.source_code, module.__dict__)
#
#
# class VirtualModuleFinder(importlib.abc.MetaPathFinder):
#     def __init__(self, module_manager):
#         self.module_manager = module_manager
#
#     def find_spec(self, fullname, path, target=None):
#         # if not fullname.startswith('virtual_modules'):
#         #     return None
#
#         loader = VirtualModuleLoader()
#         return importlib.util.spec_from_loader(fullname, loader)


@set_module_type(module_type="Managers")
class ModuleManager(ManagerController):
    """Manages dynamic loading and unloading of modules."""

    def __init__(self, system):
        super().__init__(system, table_name="modules", load_columns=[
            'uuid', 'type', 'name', 'config', 'metadata', 'locked', 'folder_path'
        ])
        # self.virtual_finder = VirtualModuleFinder(self)
        # sys.meta_path.insert(0, self.virtual_finder)

        # Initialize type controllers
        self.type_controllers = {
            None: ModulesController(system),
            "managers": ManagerModulesController(system),
            "pages": PageModulesController(system),
            "widgets": WidgetModulesController(system),
            "providers": ProviderModulesController(system),
            "members": MemberModulesController(system),
            "bubbles": BubbleModulesController(system),
            "behaviors": BehaviorModulesController(system),
        }

        self.loaded_modules: Dict[int, types.ModuleType] = {}
        self.loaded_module_hashes: Dict[int, str] = {}
        self.plugins: Dict[str, Dict[str, Type]] = {}  # {plugin_type: {name: class}}

    @override
    def load(self, import_modules: bool = True) -> None:
        """Load modules from the database and import those marked for auto-loading."""
        # Track modules to unload (those no longer in the database)
        modules_to_unload = set(self.loaded_modules.keys())
        modules_to_load = []

        # Fetch module data from the database
        modules_table = sql.get_results("""
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
                NULL,
                m.name,
                m.config,
                m.metadata,
                m.locked,
                COALESCE(fp.path, '') AS folder_path
            FROM modules m
            LEFT JOIN folder_path fp ON m.folder_id = fp.id;
        """)

        # Process module data
        for row_tuple in modules_table:
            if len(row_tuple) != len(self.load_columns):
                raise ValueError(f"Row length {len(row_tuple)} does not match expected columns {len(self.load_columns)}.")

            module_id, module_type, name, config, metadata, locked, folder_path = row_tuple
            config = json.loads(config)
            metadata = json.loads(metadata)
            folder_path = ".".join(
                convert_to_safe_case(folder) for folder in folder_path.split(".") if folder)
            module_type = folder_path.split(".")[0] if folder_path else None
            if module_type not in self.type_controllers:
                module_type = None

            row_tuple = (module_id, module_type, name, config, metadata, locked, folder_path)
            self[module_id] = row_tuple

            # Determine if module should be loaded
            auto_load = config.get("load_on_startup", False)
            if import_modules and auto_load and not locked and module_id not in self.loaded_modules:
                modules_to_load.append(module_id)
            if module_id in modules_to_unload:
                modules_to_unload.remove(module_id)

        # Load modules, retrying to handle dependencies
        while modules_to_load:
            failed = []
            for module_id in modules_to_load:
                try:
                    self.load_module(module_id)
                except Exception as e:
                    failed.append(module_id)
            # If no progress is made, avoid infinite loop
            if len(failed) == len(modules_to_load):
                print(f"Failed to load modules: {[self[mid][2] for mid in failed]}")
                break
            modules_to_load = failed

        # Unload modules no longer needed
        for module_id in modules_to_unload:
            self.unload_module(module_id)

    def load_module(self, module_id: int) -> types.ModuleType:
        """Load a single module by ID."""
        pass
    #     module_name = self.get_cell(module_id, 'name')
    #     folder_path = self.get_cell(module_id, 'folder_path')
    #     module_type = self.get_cell(module_id, 'type')
    #
    #     # Determine the import path
    #     type_controller = self.type_controllers.get(module_type)
    #     base_path = type_controller.load_to_path if type_controller is not None else None
    #
    #     if base_path is None:
    #         base_path = f'src.system.virtual_modules.{folder_path}'
    #     else:
    #         # Keep module_type only if it's the last element in the path
    #         path_parts = folder_path.split('.')
    #         if path_parts[-1] == module_type:
    #             path_parts = path_parts[:-1]
    #         folder_path = '.'.join(path_parts)
    #         if folder_path != '':
    #             base_path = f'{base_path}.{folder_path}'
    #
    #     full_module_name = f"{base_path}.{module_name}"
    #
    #     try:
    #         # Ensure parent modules exist
    #         parent_path = ".".join(full_module_name.split(".")[:-1])
    #         if parent_path and parent_path not in sys.modules:
    #             parent_module = types.ModuleType(parent_path)
    #             parent_module.__path__ = []
    #             parent_module.__package__ = ".".join(parent_path.split(".")[:-1]) or ""
    #             sys.modules[parent_path] = parent_module
    #
    #         # Import the module
    #         module = importlib.import_module(full_module_name)
    #         module.__package__ = parent_path
    #         self.loaded_modules[module_id] = module
    #         self.loaded_module_hashes[module_id] = self.get_cell(module_id, 'metadata')  # module_metadatas[module_id].get("hash", "")
    #
    #         # Register plugin if applicable
    #         module_class = self.extract_module_class(module, module_type)
    #         if module_class and hasattr(module_class, "_ap_plugin_type"):
    #             plugin_type = module_class._ap_plugin_type
    #             self.plugins.setdefault(plugin_type, {})[module_name] = module_class
    #
    #         return module
    #
    #     except ImportError as e:
    #         print(f"Error importing `{module_name}` at `{full_module_name}`: {e}")
    #         raise
    #
    def unload_module(self, module_id):
        module = self.loaded_modules.get(module_id)
        if module:
            try:
                del sys.modules[module.__name__]
            except KeyError:
                pass
            del self.loaded_modules[module_id]
            del self.loaded_module_hashes[module_id]

    # def get_cell(self, module_id, column):
    #     if isinstance(column, str):
    #         if column not in self.load_columns:
    #             raise ValueError(f"Column `{column}` not found in module table.")
    #         column = self.load_columns.index(column)
    #     return self[module_id][column]

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
                'data': textwrap.dedent(module_code),
            }

        kwargs['metadata'] = json.dumps(get_metadata(config))
        kwargs['folder_id'] = get_module_type_folder_id(module_type=folder_name) if folder_name else None

        super().add(name, **kwargs)

        main = self.system._main_gui
        if main:
            main.main_pages.build_schema()
            main.page_settings.build_schema()
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

    def get_modules_in_folder(self, folder_name=None, fetch_keys=('name',), preferred_order=None, order_column=0):
        """Returns a list of modules in the specified folder."""
        if folder_name is None:
            modules = self.type_controllers[None].get_modules(fetch_keys=fetch_keys)
        else:
            folder_name = folder_name.lower()
            if folder_name not in self.type_controllers:
                print(f"Folder `{folder_name}` not found in module types.")  # todo
                return []
            modules = self.type_controllers[folder_name].get_modules(fetch_keys=fetch_keys)

        if preferred_order:
            order_idx = {name: i for i, name in enumerate(preferred_order)}
            modules.sort(key=lambda x: order_idx.get(x[order_column], len(preferred_order)))
    
        return modules

    # def get_modules_in_folder(self, folder_name, fetch_keys=('name',)):
    #     modules =
    #     return modules
    #
    #     # folder_modules = []
    #     #
    #     # # Step 1: Process dynamically loaded modules (from database)
    #     # for module_id, module in self.loaded_modules.items():
    #     #     module_id, module_type, name, config, metadata, locked, folder_path = self[module_id]
    #     #     # module_folder = self.module_folders[module_id]
    #     #     # if module_folder != folder_name:
    #     #     #     continue
    #     #     # module_name = self.module_names[module_id]
    #     #     # module_type = self.module_types[module_id]
    #     #     class_obj = self.extract_module_class(module, module_type)
    #     #     module_item = {
    #     #         'id': module_id,
    #     #         'type': module_type,
    #     #         'name': name,
    #     #         'class': class_obj,
    #     #     }
    #     #     # Filter by fetch_keys
    #     #     if fetch_keys:
    #     #         module_item = {k: module_item[k] for k in module_item if k in fetch_keys}
    #     #     if len(module_item) == 0:
    #     #         continue
    #     #     elif len(module_item) == 1:
    #     #         module_item = module_item.get(list(module_item.keys())[0])
    #     #     folder_modules.append(tuple(module_item.values()) if isinstance(module_item, dict) else (module_item,))
    #     #
    #     #
    #     # return folder_modules
