import json
import logging
import os
import sys
import yaml
from pathlib import Path
from typing import Any, Dict, List


def get_application_path() -> str:
    """
    Gets the application's root directory.

    For development (non-frozen) environments, it finds the project root
    by looking for the 'pyproject.toml' file. For frozen executables, it uses
    platform-specific logic to determine the application's location.

    Returns:
        The absolute path to the application's root directory as a string.

    Raises:
        FileNotFoundError: If not running as a frozen executable and 'pyproject.toml'
                           cannot be found.
        NotImplementedError: If the platform is unsupported.
    """
    is_frozen = getattr(sys, 'frozen', False)

    if is_frozen:
        # --- Logic for frozen executables (kept from your original code) ---
        if sys.platform == 'win32':
            return os.path.dirname(sys.executable)

        elif sys.platform == 'linux':
            appimage_path = os.environ.get('APPIMAGE')
            if appimage_path:
                return os.path.dirname(appimage_path)
            else:
                return os.path.dirname(sys.executable)

        elif sys.platform == 'darwin':  # macOS
            return os.path.abspath(os.path.join(os.path.dirname(sys.executable), os.pardir, os.pardir, os.pardir))

        else:
            raise NotImplementedError(f"Unsupported platform for frozen executable: {sys.platform}")

    else:
        # Start from the directory of the current file (__file__)
        current_path = Path(__file__).resolve()

        # Traverse up the directory tree to find pyproject.toml
        for parent in current_path.parents:
            if (parent / 'pyproject.toml').is_file():
                # If found, we have our project root
                return str(parent)

        # If the loop completes without finding the file, raise an error.
        raise FileNotFoundError(
            "Could not find project root. "
            "The 'get_application_path' function expects a 'pyproject.toml' file in the project's root directory."
        )
    # if sys.platform == 'win32':
    #     if getattr(sys, 'frozen', False):
    #         return os.path.dirname(sys.executable)
    #
    #     return os.path.abspath(os.path.dirname(os.path.dirname(os.path.dirname(sys.executable))))
    #
    # elif sys.platform == 'linux':
    #     is_in_exe = getattr(sys, 'frozen', False)
    #     if is_in_exe:
    #         return os.path.dirname(os.environ.get('APPIMAGE'))
    #
    #     return f"{os.path.abspath(__file__).split('AgentPilot')[0]}AgentPilot"
    #
    # elif sys.platform == 'darwin':  # Mac OS todo test
    #     is_in_exe = getattr(sys, 'frozen', False)
    #     if is_in_exe:
    #         return os.path.abspath(os.path.join(os.path.dirname(sys.executable), '../../..'))
    #
    #     return f"{os.path.abspath(__file__).split('AgentPilot')[0]}AgentPilot"
    #
    # raise NotImplementedError(f"Unsupported platform: {sys.platform}")


def get_baked_dirs() -> List[Path]:
    """The core baked directory followed by each plugin's baked directory.

    In a frozen app the 'src' part is dropped, matching the `datas`
    destinations in build.spec.
    """
    if getattr(sys, 'frozen', False):
        src_path = Path(sys._MEIPASS)
    else:
        src_path = Path(get_application_path()) / 'src'
    return [
        src_path / 'utils' / 'baked',
        *sorted(src_path.glob('plugins/*/baked')),
    ]


def get_all_baked_items(table_name: str) -> Dict[Path, Dict[str, Any]]:
    """
    Finds, reads, and parses all .json and .yaml/.yml files in the
    `<table_name>` folder of every baked directory (see get_baked_dirs).

    Returns:
        A dictionary where keys are file paths and values are parsed data objects (as dictionaries).
        Empty if no items have been baked for the table yet.
    """
    parsed_files = {}
    for baked_dir in get_baked_dirs():
        data_dir = baked_dir / table_name
        if not data_dir.is_dir():
            continue

        # Process JSON files
        for file_path in data_dir.glob('*.json'):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    parsed_files[file_path] = json.load(f)
            except json.JSONDecodeError as e:
                print(f"Warning: Could not parse {file_path}. Error: {e}")
            except Exception as e:
                print(f"Warning: An unexpected error occurred while reading {file_path}. Error: {e}")

        # Process YAML files (.yaml and .yml extensions)
        for pattern in ['*.yaml', '*.yml']:
            for file_path in data_dir.glob(pattern):
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        parsed_files[file_path] = yaml.safe_load(f)
                except yaml.YAMLError as e:
                    print(f"Warning: Could not parse {file_path}. Error: {e}")
                except Exception as e:
                    print(f"Warning: An unexpected error occurred while reading {file_path}. Error: {e}")

    return parsed_files


def unsimplify_path(path):
    exe_dir = get_application_path()

    if 'AP_DEV_MODE' in os.environ.keys():
        path = path.replace('./avatars/', '/home/jb/PycharmProjects/AgentPilot/docs/avatars/')

    path = path.replace('\\', '/')

    # Handle path starting with './'
    if path.startswith('./'):
        rel_path = path[2:]  # remove the './' at the beginning
        abs_path = os.path.join(exe_dir, rel_path)
    # Handle path starting with '../'
    elif path.startswith('../'):
        parts = path.split('/')
        num_up = parts.count('..')
        rel_path = '/'.join(parts[num_up:])
        abs_path = exe_dir
        for _ in range(num_up):
            abs_path = os.path.dirname(abs_path)
        abs_path = os.path.join(abs_path, rel_path)
    # Handle path starting with '.'
    elif path.startswith('.'):
        rel_path = path[1:]
        abs_path = os.path.join(exe_dir, rel_path)
    else:
        abs_path = path

    return abs_path


def simplify_path(path):
    if path == '':
        return ''
    abs_path = os.path.abspath(path)
    exe_dir = get_application_path()

    if abs_path.startswith(exe_dir):
        rel_path = os.path.relpath(abs_path, exe_dir)
        simp_path = '.' + os.sep + rel_path
    else:
        simp_path = abs_path

    logging.debug(f'Simplified {path} to {simp_path}')
    return simp_path
