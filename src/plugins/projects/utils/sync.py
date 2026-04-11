"""Sync utilities for the Application project type.

Provides functions to mirror the source tree into a temporary directory,
detect changes made by Claude Code, and upsert modified files back into
the database as non-baked modules.
"""

import hashlib
import json
import os
import shutil

from utils import sql
from utils.filesystem import get_application_path
from utils.helpers import get_metadata, get_module_type_folder_id


def resolve_module_type(relative_path):
    """Map a file's relative path to its module type and folder id.

    Builds a reverse map from the registered type controllers, using
    longest-prefix matching against each controller's ``load_to_path``.
    Skips files whose basename starts with ``_`` or equals ``base.py``.

    Parameters
    ----------
    relative_path : str
        Path relative to ``src/``, e.g. ``plugins/workflows/providers/litellm.py``.

    Returns
    -------
    tuple[str, int] or None
        ``(module_type, folder_id)`` on success, ``None`` if the file
        cannot be mapped.
    """
    from gui import system

    basename = os.path.basename(relative_path)
    if basename.startswith('_') or basename == 'base.py':
        return None

    # Convert file path to dotted module path (strip .py)
    module_dotted = relative_path.replace(os.sep, '.').replace('/', '.')
    if module_dotted.endswith('.py'):
        module_dotted = module_dotted[:-3]

    controllers = system.manager.modules.type_controllers
    best_match = None
    best_len = 0

    for name, controller in controllers.items():
        load_path = getattr(controller, 'load_to_path', None)
        if not load_path:
            continue
        # Direct match (core modules)
        if module_dotted.startswith(load_path + '.') or module_dotted == load_path:
            if len(load_path) > best_len:
                best_len = len(load_path)
                best_match = (name, controller)
            continue
        # Cross-plugin match: plugins.<name>.<base_folder> or
        # plugins.<name>.<load_to_path> (mirrors discover_plugin_modules)
        if not module_dotted.startswith('plugins.'):
            continue
        base_folder = load_path.split('.')[-1]
        plugin_prefix_short = '.'.join(module_dotted.split('.')[:2])
        for candidate in (f'{plugin_prefix_short}.{base_folder}',
                          f'{plugin_prefix_short}.{load_path}'):
            if module_dotted.startswith(candidate + '.') or module_dotted == candidate:
                if len(candidate) > best_len:
                    best_len = len(candidate)
                    best_match = (name, controller)

    if best_match is None:
        return None

    module_type_name, controller = best_match
    folder_id = get_module_type_folder_id(
        module_type_name.replace('_', ' ').title()
    )
    return module_type_name, folder_id


def _upsert_module(source_code, folder_id, module_name):
    """Upsert a module's source code into the database."""
    config = {'data': source_code, 'name': module_name}
    metadata = get_metadata(config)
    config_json = json.dumps(config)
    metadata_json = json.dumps(metadata)

    existing_id = sql.get_scalar(
        "SELECT id FROM modules WHERE name = ? AND folder_id = ?",
        (module_name, folder_id),
    )
    if existing_id:
        sql.execute(
            "UPDATE modules SET config = ?, metadata = ? WHERE id = ?",
            (config_json, metadata_json, existing_id),
        )
    else:
        sql.execute(
            "INSERT INTO modules (name, config, metadata, folder_id, baked) "
            "VALUES (?, ?, ?, ?, 0)",
            (module_name, config_json, metadata_json, folder_id),
        )


def _reload_module(module_type_name, folder_id, module_name):
    """Reload a module in its controller and rebuild the GUI.

    Silently ignores errors so that broken code does not crash the app.
    """
    try:
        from gui import system
        from gui.util import find_main, get_selected_pages, set_selected_pages
        controller = system.manager.modules.type_controllers.get(
            module_type_name)
        if controller is None:
            return
        module_path = controller.get_module_path(module_name)
        row = sql.get_results(
            "SELECT id, uuid, name, config, metadata, '' "
            "FROM modules WHERE name = ? AND folder_id = ?",
            (module_name, folder_id),
        )
        if not row:
            return
        controller.load_db_module(module_path, row[0])
        main = find_main()
        if main:
            selections = get_selected_pages(main.main_pages)
            main.main_pages.build_schema()
            if 'settings' in main.main_pages.pages:
                main.main_pages.pages['settings'].build_schema()
            set_selected_pages(main.main_pages, selections)
    except Exception:
        pass


def sync_file_to_db(absolute_path, src_base=None):
    """Sync a single edited file to the DB if it corresponds to a module.

    Parameters
    ----------
    absolute_path : str
        Absolute path to the modified file.
    src_base : str, optional
        Project root containing ``src/``. Defaults to
        :func:`get_application_path`.

    Returns
    -------
    bool
        True if the DB was updated, False otherwise.
    """
    if not absolute_path.endswith('.py') or not os.path.isfile(absolute_path):
        return False

    src_dir = os.path.join(src_base or get_application_path(), 'src')
    if not absolute_path.startswith(src_dir + os.sep):
        return False

    relative_path = os.path.relpath(absolute_path, src_dir)
    resolved = resolve_module_type(relative_path)
    if resolved is None:
        return False

    module_type_name, folder_id = resolved
    with open(absolute_path, 'r', encoding='utf-8') as f:
        source_code = f.read()

    module_name = os.path.splitext(os.path.basename(relative_path))[0]
    _upsert_module(source_code, folder_id, module_name)
    _reload_module(module_type_name, folder_id, module_name)
    return True
