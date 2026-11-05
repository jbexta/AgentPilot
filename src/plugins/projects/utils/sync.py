"""Sync utilities for the Application project type.

Provides functions to mirror the source tree into a temporary directory,
detect changes made by Claude Code, and upsert modified files back into
the database as non-baked modules.
"""

import hashlib
import importlib
import inspect
import json
import os
import shutil
import sys

from utils import sql
from utils.filesystem import get_application_path
from utils.helpers import get_metadata, get_module_type_folder_id


def module_type_prefixes():
    """Return ``(dotted_prefix, module_type_name)`` pairs for every
    registered type controller: its ``load_to_path`` plus the plugin
    folders it loads from (``get_plugin_module_dirs``).
    """
    from gui import system

    prefixes = []
    for name, controller in system.manager.modules.type_controllers.items():
        load_path = getattr(controller, 'load_to_path', None)
        if not load_path:
            continue
        prefixes.append((load_path, name))
        prefixes.extend(
            (dotted, name)
            for _, dotted in controller.get_plugin_module_dirs()
        )
    return prefixes


def resolve_module_type_name(relative_path, prefixes=None):
    """Map a file's relative path to its module type name.

    Uses longest-prefix matching against ``module_type_prefixes()``.
    Skips files whose basename starts with ``_`` or equals ``base.py``.

    Parameters
    ----------
    relative_path : str
        Path relative to ``src/``, e.g. ``plugins/workflows/providers/litellm.py``.
    prefixes : list, optional
        Precomputed ``module_type_prefixes()``, for resolving many files.

    Returns
    -------
    str or None
        The module type name, ``None`` if the file cannot be mapped.
    """
    basename = os.path.basename(relative_path)
    if basename.startswith('_') or basename == 'base.py':
        return None

    # Convert file path to dotted module path (strip .py)
    module_dotted = relative_path.replace(os.sep, '.').replace('/', '.')
    if module_dotted.endswith('.py'):
        module_dotted = module_dotted[:-3]

    best_match = None
    best_len = 0
    for prefix, name in prefixes or module_type_prefixes():
        if module_dotted.startswith(prefix + '.') and len(prefix) > best_len:
            best_len = len(prefix)
            best_match = name
    return best_match


def resolve_module_type(relative_path):
    """Map a file's relative path to ``(module_type, folder_id)``."""
    module_type_name = resolve_module_type_name(relative_path)
    if module_type_name is None:
        return None
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


def _reload_module(module_type_name, folder_id, module_name, module_path):
    """Reload a module in its controller.

    Silently ignores errors so that broken code does not crash the app.
    """
    try:
        from gui import system
        controller = system.manager.modules.type_controllers.get(
            module_type_name)
        if controller is None:
            return
        row = sql.get_results(
            "SELECT id, uuid, name, config, metadata, '' "
            "FROM modules WHERE name = ? AND folder_id = ?",
            (module_name, folder_id),
        )
        if not row:
            return
        controller.load_db_module(module_path, row[0])
    except Exception:
        pass


def get_modified_module_files(src_base=None):
    """Return paths of module files whose source differs from the DB."""
    src_dir = os.path.join(src_base or get_application_path(), 'src')
    stored_sources = {
        (name, folder_name): data
        for name, folder_name, data in sql.get_results(
            "SELECT m.name, REPLACE(LOWER(f.name), ' ', '_'), "
            "json_extract(m.config, '$.data') "
            "FROM modules m JOIN folders f ON f.id = m.folder_id "
            "WHERE f.type = 'modules'"
        )
    }
    prefixes = module_type_prefixes()
    modified = []
    for dirpath, dirnames, filenames in os.walk(src_dir):
        dirnames[:] = [d for d in dirnames if d != '__pycache__']
        for fn in filenames:
            if not fn.endswith('.py'):
                continue
            fp = os.path.join(dirpath, fn)
            module_type_name = resolve_module_type_name(
                os.path.relpath(fp, src_dir), prefixes)
            if module_type_name is None:
                continue
            stored = stored_sources.get((os.path.splitext(fn)[0], module_type_name.lower()))
            if stored is None:
                continue
            with open(fp, 'r', encoding='utf-8') as f:
                if f.read().rstrip('\n') != stored.rstrip('\n'):
                    modified.append(fp)
    return modified


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
    module_path = os.path.splitext(relative_path)[0].replace(os.sep, '.')
    _reload_module(module_type_name, folder_id, module_name, module_path)
    return True


def is_project_module(module):
    src_dir = os.path.join(get_application_path(), 'src') + os.sep
    path = getattr(module, '__file__', None)
    return bool(path) and os.path.abspath(path).startswith(src_dir)


def project_imports(module):
    """Return the project modules referenced by *module*'s globals."""
    names = {
        v.__name__ if inspect.ismodule(v) else getattr(v, '__module__', None)
        for v in vars(module).values()
    }
    return [
        sys.modules[n] for n in names - {module.__name__}
        if n in sys.modules and is_project_module(sys.modules[n])
    ]


def snapshot_mtimes():
    """Return ``{path: mtime}`` for every ``.py`` file under ``src``."""
    src_dir = os.path.join(get_application_path(), 'src')
    mtimes = {}
    for dirpath, dirnames, filenames in os.walk(src_dir):
        dirnames[:] = [d for d in dirnames if d != '__pycache__']
        for fn in filenames:
            if fn.endswith('.py'):
                fp = os.path.abspath(os.path.join(dirpath, fn))
                mtimes[fp] = os.path.getmtime(fp)
    return mtimes


def changed_files(old, new):
    """Return the files added or changed between two mtime snapshots."""
    return {fp for fp, mtime in new.items() if old.get(fp) != mtime}


def reload_stale(modules, changed):
    """Reload each module whose file is in *changed*, or importing one that
    is, dependencies first."""
    stale = {}

    def visit(module):
        name = module.__name__
        if name not in stale:
            stale[name] = False
            deps_stale = [visit(dep) for dep in project_imports(module)]
            stale[name] = (
                any(deps_stale)
                or os.path.abspath(module.__file__) in changed
            )
            if stale[name]:
                importlib.reload(module)
        return stale[name]

    for module in modules:
        visit(module)
