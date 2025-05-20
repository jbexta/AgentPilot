
import importlib
import inspect
import json
import sys
import textwrap
from importlib.util import resolve_name

from typing_extensions import override

from src.utils import sql
from src.utils.helpers import convert_to_safe_case, get_metadata, get_module_type_folder_id, set_module_type, \
    ManagerController
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
            # get module_id (key) from the self.module_manager.module_name dict where value is module_name
            # module_id = get_key_by_value(
            #     d=self.module_manager.module_name,
            #     value=module_name
            # )
            module_id = self.module_manager.folder_modules.get(parent_folder, {}).get(module_name)
            if module_id:
                loader = VirtualModuleLoader(self.module_manager, module_id)
                return importlib.util.spec_from_loader(fullname, loader)

        return None


@set_module_type(module_type='Managers')
class ModuleManager(ManagerController):
    def __init__(self, parent):
        super().__init__(parent, table_name='modules')
        # self.modules = {}
        self.module_names = {}
        self.module_types = {}
        self.module_metadatas = {}
        self.module_folders = {}

        self.loaded_modules = {}
        self.loaded_module_hashes = {}

        self.folder_modules = {}

        self.plugins = {}  # {plugin group: {plugin name: plugin class}}

        self.special_types = {
            'Managers': {
                'import_path': 'src.system',
            },
            'Bubbles': {
                'import_path': 'src.gui.bubbles',
            },
            'Providers': {
                'import_path': 'src.system.providers',
            },
            'Widgets': {
                'import_path': 'src.system.widgets',
            }
        }

        self.virtual_modules = types.ModuleType('virtual_modules')
        self.virtual_modules.__path__ = []
        sys.modules['virtual_modules'] = self.virtual_modules
        sys.meta_path.insert(0, VirtualModuleFinder(self))

    @override
    def load(self, import_modules=True):
        # Keep track of existing loaded modules that need to be unloaded
        modules_to_unload = set(self.loaded_modules.keys())

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
                m.locked,
                COALESCE(fp.path, '') AS folder_path
            FROM modules m
            LEFT JOIN folder_path fp 
                ON m.folder_id = fp.id;""")
        for module_id, name, config, metadata, locked, folder_path in modules_table:
            config = json.loads(config)
            folder_path = '.'.join([convert_to_safe_case(folder) for folder in folder_path.split('~#@~#$~#£~#&~')])
            folder_name = folder_path.split('.')[0]

            self[module_id] = config
            self.module_names[module_id] = name
            self.module_metadatas[module_id] = json.loads(metadata)
            self.module_folders[module_id] = folder_path
            self.module_types[module_id] = None if not folder_name in self.special_types else folder_name

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
            if module_id not in self.loaded_modules and import_modules and auto_load and not locked == 1:
                modules_to_load.append(module_id)
            elif module_id in self.loaded_modules and module_id in modules_to_unload:
                modules_to_unload.remove(module_id)

        # do this for now to avoid managing import dependencies
        load_count = 1
        while load_count > 0:
            load_count = 0
            modules_done = []
            for module_id in modules_to_load:
                res = self.load_module(module_id)
                if isinstance(res, Exception):
                    continue
                modules_done.append(module_id)
                load_count += 1

            modules_to_load = [m for m in modules_to_load if m not in modules_done]

        # Unload any modules that weren't reloaded
        for module_id in modules_to_unload:
            self.unload_module(module_id)

        modules_string = ', '.join([self.module_names[m] for m in self.loaded_modules.keys()])
        print(f"Loaded {len(self.loaded_modules)} modules:\n\n{modules_string}")

    def load_module(self, module_id):
        module_name = self.module_names[module_id]
        folder_path = self.module_folders[module_id]

        try:
            module_type = folder_path.split('.')[0]
            custom_parent = None
            if module_type in self.special_types:
                custom_parent = self.special_types[module_type].get('import_path')
            if custom_parent:
                full_module_name = f'{custom_parent}.{module_name}'
            else:
                # Create parent modules if they don't exist
                full_module_name = f'virtual_modules.{folder_path}.{module_name}'
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

            if full_module_name in sys.modules:
                self.unload_module(module_id)

            # Now import the actual module
            parent_module_path = '.'.join(full_module_name.split('.')[:-1])
            module = importlib.import_module(full_module_name)
            module.__dict__['__package__'] = parent_module_path

            self.loaded_modules[module_id] = module
            self.loaded_module_hashes[module_id] = self.module_metadatas[module_id].get('hash')

            # module_folder = self.module_folders[module_id]
            # module_class = self.get_module_class(
            #     module_type=module_folder,
            #     module_name=self.module_names[module_id]
            # )
            module_class = self.loaded_modules[module_id]
            if module_class and '_ap_plugin_type' in module_class.__dict__:
                plugin_type = module_class._ap_plugin_type
                if plugin_type not in self.plugins:
                    self.plugins[plugin_type] = {}
                self.plugins[plugin_type][self.module_names[module_id]] = module_class

            return module

        except Exception as e:
            print(f"Error importing `{module_name}`: {e}")
            return e

    def unload_module(self, module_id):
        module = self.loaded_modules.get(module_id)
        if module:
            try:
                del sys.modules[module.__name__]
            except KeyError:
                pass
            del self.loaded_modules[module_id]
            del self.loaded_module_hashes[module_id]

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

    def get_module_class(self, module_type, module_name, default=None):
        # get the loaded module from self  # todo lower()
        # module_id = next(key for key in self.folder_modules.keys() if key.lower() == module_name.lower())
        folder_type_modules = self.folder_modules.get(module_type.lower(), {})
        module_id = next((value for key, value in folder_type_modules.items() if key.lower() == module_name.lower()), None)
        # module_id = folder_type_modules.get(module_name)
        module = self.loaded_modules.get(module_id)

        # module_defaults = {
        #     'managers': 'src.system.managers',
        #     'bubbles': 'src.gui.bubbles',
        #     'providers': 'src.system.providers',
        # }
        # if module_type in self.module_
        special_class = self._extract_class_from_module(module, module_type, default)
        return special_class

    def _extract_class_from_module(self, module, module_type, default=None):
        if not module:
            return default
        all_module_classes = [(name, obj) for name, obj in inspect.getmembers(module) if
                              inspect.isclass(obj) and obj.__module__ == module.__name__]

        if len(all_module_classes) == 0:
            raise ValueError(f"Module `{module.__name__}` has no classes.")

        if len(all_module_classes) == 1:
            return all_module_classes[0][1]

        marked_module_classes = [(name, obj) for name, obj in all_module_classes if
                                 getattr(obj, '_ap_module_type', '') == module_type]
        if len(marked_module_classes) == 1:
            return marked_module_classes[0][1]

        elif len(marked_module_classes) > 1:
            raise ValueError(f"Module `{module.__name__}` has multiple classes marked as `{module_type}`"
                             f"Please ensure there is only one class marked with the decorator `@set_module_type(module_type)`")
        else:
            raise ValueError(f"Module `{module.__name__}` has multiple classes: {', '.join([name for name, _ in all_module_classes])}. "
                             f"Please mark your class with the decorator `@set_module_type(module_type)`")

    # todo remove
    def get_modules_in_folder(self, folder_name, fetch_keys=('name',)):
        # THIS SHOULD RETURN ALL MODULES IN THE FOLDER AS A LIST OF DICTS WITH ITEMS:
        #   - module_id, module_uuid, module_name, class_obj, module_type
        folder_modules = []
        for module_id, module in self.loaded_modules.items():
            module_folder = self.module_folders[module_id]
            if module_folder != folder_name:
                continue
            module_name = self.module_names[module_id]
            module_type = self.module_types[module_id]
            class_obj = self._extract_class_from_module(module, module_type)
            module_item = {
                'id': module_id,
                'uuid': None,
                'name': module_name,
                'type': module_type,
                'class': class_obj,
            }
            # remove keys not in fetch_keys
            if fetch_keys:
                module_item = {k: module_item[k] for k in module_item if k in fetch_keys}
            if len(module_item) == 0:
                continue
            elif len(module_item) == 1:
                module_item = module_item.get(list(module_item.keys())[0])

            folder_modules.append(tuple(module_item.values()))

        return folder_modules


# def get_module_definitions(module_type='managers', with_ids=False):
#     from src.system import manager
#     custom_defs = {}
#
#     # get custom modules from modules
#     module_manager = manager.modules
#     for module_id, module in module_manager.loaded_modules.items():
#         folder = module_manager.module_folders[module_id]
#         module_name = module_manager.module_names[module_id]
#         if folder != module_type:
#             continue
#
#         all_module_classes = [(name, obj) for name, obj in inspect.getmembers(module) if inspect.isclass(obj) and obj.__module__ == module.__name__]
#         marked_module_classes = [(name, obj) for name, obj in all_module_classes if getattr(obj, '_ap_module_type', False)]
#         all_module_classes += marked_module_classes
#
#         if len(all_module_classes) == 0:
#             continue
#
#         first_valid_class = next(
#             iter([(name, obj) for name, obj in all_module_classes if getattr(obj, '_ap_module_type', False)]),
#             None)
#         if not first_valid_class:
#             first_valid_class = next(iter(all_module_classes), None)
#
#         _, class_obj = first_valid_class
#         key = module_name if not with_ids else (module_id, module_name)
#         custom_defs[key] = class_obj
#
#     # get custom modules from src/plugins/addons
#     if 'AP_DEV_MODE' in os.environ.keys():
#         this_file_path = os.path.abspath(__file__)
#         project_source_path = os.path.dirname(os.path.dirname(this_file_path))
#         addons_path = os.path.join(project_source_path, 'plugins', 'addons')
#         addons_names = [name for name in os.listdir(addons_path) if not name.endswith('.py')]
#         for addon_name in addons_names:
#             addon_module_type_path = os.path.join(addons_path, addon_name, module_type)
#             if not os.path.exists(addon_module_type_path):
#                 continue
#             for filename in os.listdir(addon_module_type_path):
#                 if filename.startswith('_') or not filename.endswith('.py'):
#                     continue
#                 module_name = filename[:-3]
#                 module = __import__(f'plugins.addons.{addon_name}.{module_type}.{module_name}', fromlist=[''])
#
#                 # Find the class definitions in the module, prioritizing classes with _ap_module_type = True
#
#                 all_module_classes = [(name, obj) for name, obj in inspect.getmembers(module) if inspect.isclass(obj) and obj.__module__ == module.__name__]
#                 marked_module_classes = [(name, obj) for name, obj in all_module_classes if getattr(obj, '_ap_module_type', False)]
#                 all_module_classes = marked_module_classes + all_module_classes
#
#                 if len(all_module_classes) == 0:
#                     continue
#
#                 first_valid_class = next(iter([(name, obj) for name, obj in all_module_classes if getattr(obj, '_ap_module_type', False)]), None)
#                 if not first_valid_class:
#                     first_valid_class = next(iter(all_module_classes), None)
#
#                 _, class_obj = first_valid_class
#                 key = module_name if not with_ids else (None, module_name)
#                 custom_defs[key] = class_obj
#                 break
#
#     return custom_defs
