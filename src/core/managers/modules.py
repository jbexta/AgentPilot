import importlib
import inspect
import json
import os
import pkgutil
import sys
import textwrap
import time
import types
from typing import Dict

from typing_extensions import override

from utils import sql
from utils.helpers import hash_config, set_module_type, get_metadata, get_module_type_folder_id, BaseManager
# import types


@set_module_type(module_type="Managers")
class ModuleManager(BaseManager):
    """Manages dynamic loading and unloading of modules."""

    def __init__(self, system):
        super().__init__(system, table_name="modules", store_data=False)
        self.type_controllers: Dict[str, ModulesController] = {
            'controllers': ModulesController(
                system=system,
                module_type='controllers',
                load_to_path='core.controllers',
            )
        }
    
    def reload_controllers(self):
        self.type_controllers['controllers'].load()
        all_controllers = self.get_modules_in_folder(
            module_type='Controllers',
            fetch_keys=('name', 'class',)
        )
        for name, controller_cls in all_controllers:
            if name in self.type_controllers:
                continue
            if controller_cls:
                self.type_controllers[name] = controller_cls(self)

    @override
    def load(self):
        self.reload_controllers()

        for type_controller in self.type_controllers.values():
            type_controller.load()

    def get_modules_in_folder(self, module_type, fetch_keys=('name',)):
        """Returns a list of modules in the specified folder."""
        type_controller = self.type_controllers.get(module_type.lower())
        if type_controller is None:
            print(f"Folder `{module_type}` not found in module types.")  # todo
            return []

        modules = type_controller.get_modules(fetch_keys=fetch_keys)
        return modules

    def get_module_class(self, module_type, module_name, default=None):
        """Returns the class of a module by its type and module name."""
        if module_name is None:
            raise NotImplementedError('')
        type_modules = self.get_modules_in_folder(module_type, fetch_keys=('name', 'class',))
        module_class = next((value for key, value in type_modules if key.lower() == module_name.lower()), default)
        return module_class

    @override
    def add(self, name, **kwargs):
        module_type = kwargs.pop('module_type', None)
        if module_type:
            module_type = module_type.lower()
        if module_type is not None and module_type not in self.type_controllers:
            raise NotImplementedError(f'Folder `{module_type}` not found in module types.')
        
        type_controller = self.type_controllers.get(module_type)

        config = kwargs.get('config', {})
        if not config and type_controller:
            if hasattr(type_controller, 'initial_content'):

                module_code = type_controller.initial_content(name)
                config = {
                    'load_on_startup': True,
                    'data': textwrap.dedent(module_code),
                }

        # kwargs['locked'] = 1
        module_type = module_type.replace('_', ' ').title()
        metadata = get_metadata(config)
        extra_metadata = kwargs.pop('extra_metadata', None)
        if extra_metadata:
            metadata.update(extra_metadata)
        kwargs['config'] = config
        kwargs['metadata'] = json.dumps(metadata)
        kwargs['folder_id'] = get_module_type_folder_id(module_type) if module_type else None

        super().add(name, **kwargs)

        # Materialise the module on disk so Claude Code / IDEs can see a
        # real file. In source mode we auto-bake (real source-import
        # path + __file__). In frozen mode we write to the mirror
        # alongside the executable but keep ``baked=0`` because the
        # bundled source isn't writable.
        if type_controller is None:
            return
        is_frozen = getattr(sys, 'frozen', False)
        if is_frozen:
            type_controller.write_mirror_file(name)
        else:
            auto_bake = self.system.config.get('system.auto_bake', False)
            if auto_bake:
                type_controller.bake_module(name)

    # def test_modules(self):
    #     for module_type in self.type_controllers:
    #         controller = self.type_controllers[module_type]
    #         is_class_based = controller.class_based
    #         inherit_from = controller.inherit_from

    #         if is_class_based:
    #             for name, info in controller.items():
    #                 module_item = info
    #                 cl = module_item[3]
    #                 if cl is not None:
    #                     pass
    #                 pass
        
    #     return True


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


def ensure_parent_modules(module_name):
    """Ensure parent modules exist in sys.modules."""
    if not module_name:
        return
    parts = module_name.split(".")
    for i in range(1, len(parts)):
        parent_path = ".".join(parts[:i])
        if parent_path not in sys.modules:
            print(f"Creating parent module: {parent_path}")
            parent_module = types.ModuleType(parent_path)
            parent_module.__path__ = []
            parent_module.__package__ = ".".join(parts[:i - 1]) or ""
            sys.modules[parent_path] = parent_module


class ModulesController(BaseManager):
    def __init__(
            self,
            system,
            module_type=None,
            load_to_path='src.system.modules',
            class_based=False,
            inherit_from=None,
            description=None,
            long_description=None,
            **kwargs
    ):
        kwargs['table_name'] = 'modules'
        kwargs['load_columns'] = ['id', 'uuid', 'name', 'config', 'class', 'kind_folder', 'metadata', 'hash', 'baked', 'folder_path']
        super().__init__(system, **kwargs)

        self.module_type = module_type
        self.load_to_path = load_to_path
        self.description = description
        self.long_description = long_description
        self.class_based = class_based
        self.inherit_from = inherit_from

    def load(self):
        """
        Loads and registers modules of the specified type from the database and source code.
        """
        if self.module_type is not None:
            self.load_source_modules()

        allow_db = sql.get_scalar("""
            SELECT json_extract(value, '$."system.allow_importing_db_modules"')
            FROM settings WHERE field = 'app_config'
        """)
        
        if not allow_db:
            return

        rows = sql.get_results(f"""
            WITH RECURSIVE folder_path AS (
                SELECT id, name, parent_id, name AS path
                FROM folders
                WHERE parent_id IS NULL AND LOWER(name) = ?
                UNION ALL
                SELECT f.id, f.name, f.parent_id, fp.path || '.' || f.name
                FROM folders f
                JOIN folder_path fp ON f.parent_id = fp.id
            )
            SELECT
                m.id,
                m.uuid,
                m.name,
                m.config,
                m.metadata,
                fp.path AS folder_path
            FROM modules m
            JOIN folder_path fp ON m.folder_id = fp.id
	        WHERE m.baked = 0
        """, (self.module_type,))

        for row in rows:
            module_name = row[2]

            module_path = self.get_module_path(module_name)
            self.load_db_module(module_path, row)

    def load_db_module(self, module_path, row):
        db_id, uuid, module_name, config, metadata, folder_path = row
        metadata = json.loads(metadata)

        # Remove old module if exists
        if module_path in sys.modules:
            del sys.modules[module_path]

        ensure_parent_modules(module_path)
        # Create and execute module
        config = json.loads(config)
        source_code = config.get('data', '')

        from gui.pages.modules import get_module_abs_path
        mirror_path = get_module_abs_path(db_id, module_name=module_name)
        origin = str(mirror_path) if mirror_path and os.path.isfile(mirror_path) else None

        loader = VirtualModuleLoader(source_code)
        spec = importlib.util.spec_from_loader(module_path, loader, origin=origin)
        module = importlib.util.module_from_spec(spec)
        if origin:
            module.__file__ = origin
        sys.modules[module_path] = module
        try:
            spec.loader.exec_module(module)
        except Exception as e:
            print(f"Error executing module {module_path}: {str(e)}")
            return
        module.__package__ = '.'.join(module_path.split('.')[:-1])
        # module.__name__ = module_path  # Ensure the module name is set correctly

        # Register the module
        cls = self.extract_module_class(module_name, default=None)
        kind_folder = None
        hash = metadata.get('hash')
        self[module_name] = (db_id, uuid, module_name, config, cls, kind_folder, metadata, hash, 0, folder_path)

    def _resolve_module_db_id(self, module_name):
        folder_id = (
            get_module_type_folder_id(self.module_type)
            if self.module_type else None
        )
        return sql.get_scalar(
            "SELECT id FROM modules WHERE name = ? AND folder_id = ?",
            (module_name, folder_id),
        )

    def _write_module_source_to_disk(self, module_name):
        """Write this module's DB source to ``get_module_abs_path``.

        Returns the path that was written, or ``None`` if the module or
        its target path cannot be resolved. Creates parent directories
        as needed; overwrites any existing file.
        """
        from gui.pages.modules import get_module_abs_path

        db_id = self._resolve_module_db_id(module_name)
        if db_id is None:
            return None
        config = sql.get_scalar(
            "SELECT config FROM modules WHERE id = ?",
            (db_id,), load_json=True,
        ) or {}
        source_code = config.get('data', '')
        target = get_module_abs_path(db_id, module_name=module_name)
        if target is None:
            return None
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, 'w', encoding='utf-8') as f:
            f.write(source_code)
        return target

    def bake_module(self, module_name):
        """Write the module to ``src/<load_to_path>/<name>.py`` and mark
        the DB row as ``baked=1`` so subsequent loads use the real
        source-import path.

        Idempotent: safe to call on an already-baked module.
        """
        target = self._write_module_source_to_disk(module_name)
        if target is None:
            return None
        db_id = self._resolve_module_db_id(module_name)
        if db_id is not None:
            sql.execute(
                "UPDATE modules SET baked = 1 WHERE id = ?", (db_id,)
            )
        return target

    def write_mirror_file(self, module_name):
        """Write the module's source to the on-disk mirror without
        touching the ``baked`` flag. Used in frozen mode so Claude Code
        and the user's IDE can see a real file while the DB loader
        still owns module execution.
        """
        return self._write_module_source_to_disk(module_name)

    def load_source_modules(self):
        """
        Loads source modules by discovering them, importing, extracting their classes,
        and storing them.
        """

        if self.load_to_path == 'plugins.workflows.providers':
            pass
        discovered_module_infos = self.discover_modules(self.load_to_path)

        # Discover modules from other plugins that provide this module type
        plugin_module_infos = self.discover_plugin_modules()
        # Iterate core first, plugins second so that plugin-sourced modules
        # always win the ``self[module_name]`` assignment when a same-named
        # module exists in both (e.g. a stale bug-written core duplicate of
        # a plugin module). Plugin modules carry the 11th-slot origin that
        # ``get_module_file_path`` needs to route writes correctly; a core
        # entry would leave it ``None`` and writes would drift back to the
        # core codebase. Using a set union here would be non-deterministic.
        all_module_infos = list(discovered_module_infos) + list(plugin_module_infos)

        folder_id = get_module_type_folder_id(self.module_type)
        for cls, module_path_str, kind_folder in all_module_infos:
            module_name = module_path_str.split('.')[-1]
            module = sys.modules[module_path_str]
            try:
                source_code = inspect.getsource(module)
            except TypeError:
                # DB-backed VirtualModuleLoader override; already tracked in DB.
                continue
            config = {'data': source_code, "name": module_name}
            metadata = get_metadata(config)

            db_id = sql.get_scalar(
                "SELECT id FROM modules WHERE name = ? AND folder_id = ?",
                (module_name, folder_id)
            )

            if db_id is None:
                metadata_json = json.dumps(metadata)
                sql.execute("""
                    INSERT INTO modules (name, config, folder_id, metadata, baked, locked)
                    VALUES (?, ?, ?, ?, 1, 1)
                """, (module_name, json.dumps(config), folder_id, metadata_json))
                db_id = sql.get_scalar(
                    "SELECT id FROM modules WHERE name = ? AND folder_id = ?",
                    (module_name, folder_id)
                )

            # Preserve enabled state from DB config
            if db_id is not None:
                db_enabled = sql.get_scalar(
                    "SELECT json_extract(config, '$.enabled') FROM modules WHERE id = ?",
                    (db_id,)
                )
                if db_enabled is not None:
                    config['enabled'] = bool(db_enabled)

            if cls:  # Ensure a class was indeed found and extracted
                # In-memory-only 11th slot: the parent package dotted path
                # when the module was discovered under ``src/plugins/...``
                # (e.g. ``plugins.my_plugin.providers`` for a module at
                # ``plugins.my_plugin.providers.foo``), else ``None``. Used
                # by ``gui.pages.modules.get_module_file_path`` to route
                # bake / mirror writes back to the plugin directory instead
                # of the core ``load_to_path``. Repopulated on each startup.
                plugin_package = (
                    module_path_str.rsplit('.', 1)[0]
                    if module_path_str.startswith('plugins.')
                    else None
                )
                self[module_name] = (
                    db_id,  # DB id (may be None if not in database)
                    None,  # UUID (not applicable for source modules)
                    module_name,  # Simple name of the module
                    config,  # Config
                    cls,  # The extracted class from the module
                    kind_folder,  # Kind folder
                    metadata,  # Metadata
                    hash_config(config), # Hash
                    1,  # Baked (source modules are baked)
                    '',  # Folder path (can be derived if needed, or left empty)
                    plugin_package,  # Plugin parent package (in-memory only)
                )

    def discover_modules(self, package_path: str, discovered_items=None):
        """
        Discovers modules within a given package path, imports them,
        and extracts the relevant class.
        Returns a set of (class_object, module_full_path_str, kind_folder) tuples.
        """
        if discovered_items is None:
            discovered_items = set()

        try:
            package_module = importlib.import_module(package_path)
            # Ensure __path__ is present; pkgutil.iter_modules requires it.
            if not hasattr(package_module, '__path__'):
                # This might be a single file module acting as a "package path".
                # Handling this case might require treating package_path itself as a module to inspect.
                # For now, assume package_path is always a directory-based package.
                print(f"Warning: {package_path} is not a package or has no __path__.")
                return discovered_items
        except ImportError as e:
            print(f"Could not import package: {package_path}. Error: {e}")
            return discovered_items

        for _, name, is_pkg in pkgutil.iter_modules(package_module.__path__, prefix=package_module.__name__ + '.'):
            # pkgutil with prefix gives the full path directly (e.g., src.gui.pages.some_page)
            # The 'name' variable from iter_modules will be the full path if prefix is used.
            # Let's call it inner_module_full_path for clarity.
            inner_module_full_path = name

            leaf = name.split('.')[-1]
            if leaf == 'base' or leaf.startswith('_'):
                continue
            # ``gui`` and ``core`` are reserved for the plugin-root layout
            # (handled by ``get_plugin_module_dirs``) and are never valid as
            # nested directories inside a module-type folder. Skipping them
            # here prevents the recursive walk from picking up stray
            # subfolders by those names and silently registering modules
            # under colliding simple names / writing bakes to the wrong path.
            if is_pkg and leaf in ('gui', 'core'):
                continue

            if is_pkg:
                self.discover_modules(inner_module_full_path, discovered_items)  # Recurse for sub-packages
            else:
                try:
                    # 1. Explicitly import the individual module file.
                    # This places it into sys.modules.
                    actual_module_object = importlib.import_module(inner_module_full_path)

                    # 2. Extract the class from the *actual* module object.
                    cls = self.extract_module_class(actual_module_object, default=None)

                    if cls:
                        kind_folder = None
                        # if '.' x2 is in the path
                        dot_count = inner_module_full_path.count('.')
                        if dot_count > 1:
                            folder_name = inner_module_full_path.split('.')[-2]
                            if folder_name != self.module_type:
                                kind_folder = folder_name
                                
                        discovered_items.add((cls, inner_module_full_path, kind_folder))
                    else:
                        # Optional: Log if no suitable class was found in a discovered module.
                        # print(f"No suitable class found in module: {inner_module_full_path} for type {self.module_type}")
                        pass
                except ImportError as e:
                    print(f"Failed to import or process module {inner_module_full_path}: {e}")
                except Exception as e:  # Catch other potential errors during class extraction
                    print(f"Error extracting class from module {inner_module_full_path}: {e}")
        return discovered_items

    def get_plugin_module_dirs(self):
        """Get all plugin directories that provide modules for *load_to_path*.

        Checks two folder layouts per plugin:
        1. ``plugins/<name>/<base_folder>/``
        2. ``plugins/<name>/<load_to_path as path>/``

        Yields ``(fs_path, dotted_path)`` for each match.
        """
        base_folder = self.load_to_path.split('.')[-1]

        # Get all plugin directories
        plugins_dir = "src/plugins"

        if not os.path.isdir(plugins_dir):
            return

        for plugin_name in os.listdir(plugins_dir):
            plugin_path = os.path.join(plugins_dir, plugin_name)

            # Skip non-directories and special directories
            if not os.path.isdir(plugin_path) or plugin_name.startswith('_'):
                continue

            # Check if the plugin has the base_folder subdirectory
            base_folder_path = os.path.join(plugin_path, base_folder)
            base_real_folder_path = os.path.join(plugin_path, self.load_to_path.replace('.', os.sep))

            if os.path.isdir(base_folder_path):
                # Convert to module path format
                yield base_folder_path, f"plugins.{plugin_name}.{base_folder}"
            elif os.path.isdir(base_real_folder_path):
                yield base_real_folder_path, f"plugins.{plugin_name}.{self.load_to_path}"

    def discover_plugin_modules(self):
        """
        Discovers modules within plugin directories.
        Searches through src/plugins/*/base_folder for modules.
        Returns a set of (class_object, module_full_path_str) tuples.
        """
        discovered_items = set()
        for _fs_path, dotted_path in self.get_plugin_module_dirs():
            # Use the existing discover_modules method to scan this path
            try:
                plugin_modules = self.discover_modules(dotted_path, set())
                discovered_items.update(plugin_modules)
            except Exception as e:
                print(f"Error discovering modules in {dotted_path}: {e}")
        return discovered_items

    def get_modules(self, fetch_keys=('name',)):
        """
        Returns module information based on loaded modules.
        """
        if self.module_type.lower() == 'pages':
            pass
        type_modules = []

        for name, info in self.items():
            module_item = info

            if isinstance(module_item, tuple):
                module_item = {
                    'id': module_item[0],
                    'uuid': module_item[1],
                    'name': module_item[2],
                    'config': module_item[3],
                    'class': module_item[4],
                    'kind_folder': module_item[5],
                    'metadata': module_item[6],
                    'hash': module_item[7],
                    'baked': module_item[8],
                    'folder_path': module_item[9]
                }

            if module_item['class'] is None:
                print(f"Module `{module_item['name']}` has no class defined.")
                continue

            if not module_item.get('config', {}).get('enabled', True):
                continue

            # if fetch_keys:
            # module_item = {k: v for k, v in module_item.items() if k in fetch_keys}
            # order by fetch_keys
            module_item = {k: module_item[k] for k in fetch_keys}

            module_values = tuple(module_item.values())
            type_modules.append(module_values)

        # Sort to ensure consistent ordering
        type_modules.sort(key=lambda x: x[fetch_keys.index('name')] if 'name' in fetch_keys else x[0])

        if len(fetch_keys) == 1:
            type_modules = [item[0] for item in type_modules]

        return type_modules

    def get_module_path(self, module_name):
        """
        Returns the module object by its name, using `load_to_path` as the base path.
        """
        base_path = self.load_to_path if self.load_to_path else 'src'
        return f"{base_path}.{module_name}"

    def extract_module_class(self, module_or_name, default=None):
        """Extract the class from a module that matches the module_type."""
        if isinstance(module_or_name, str):
            module_path = self.get_module_path(module_or_name)
            module_object = sys.modules.get(module_path)
            if not module_object:
                # Attempt to import it if it's missing; this is a fallback.
                # Ideally, it should have been imported during the discover_modules phase.
                try:
                    module_object = importlib.import_module(module_path)
                except ImportError:
                    print(f"Module {module_path} not found in sys.modules and could not be imported.")
                    return default
        else: # It's already a module object
            module_object = module_or_name

        if not module_object:
            # This case should ideally not be reached if discovery and loading are correct.
            print(f"Could not resolve module: {module_or_name}")
            return default

        # Get all module classes defined ONLY in the module
        all_module_classes = [
            (name, obj) for name, obj in inspect.getmembers(module_object, inspect.isclass)
            if getattr(obj, '__module__', '').startswith(module_object.__name__)
        ]

        marked_module_classes = [
            (name, obj) for name, obj in all_module_classes
            if obj.__dict__.get('_ap_module_type') == self.module_type
        ]

        if len(all_module_classes) == 1 and not marked_module_classes:
             # If only one class is defined in the module, and none are marked, assume it's the one.
            candidate_class = all_module_classes[0][1]
            # Optionally, you might want to check if this single class should still have _ap_module_type
            # For now, let's assume if it's the *only* class, it's the intended one.
            # print(f"Module `{module_object.__name__}` has one class, using it as default.")
            return candidate_class


        if not marked_module_classes:
            if all_module_classes: # If there are classes, but none are marked
                # print(f"Module `{module_object.__name__}` has classes, but none are marked as type `{self.module_type}`. Available: {[n for n,o in all_module_classes]}")
                pass # Fall through to return default
            else: # No classes at all
                # print(f"Module `{module_object.__name__}` has no classes.")
                pass
            return default

        if len(marked_module_classes) > 1:
            print(f"Warning: Module `{module_object.__name__}` has multiple classes marked as type `{self.module_type}`. Using the first one: {marked_module_classes[0][0]}.")
            # Potentially return default or raise an error, or just take the first one.
            # return default
            return marked_module_classes[0][1]


        return marked_module_classes[0][1]