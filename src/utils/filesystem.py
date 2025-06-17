import json
import logging
import os
import sys
from pathlib import Path
from typing import List, Any, Dict


def get_application_path() -> str:
    """
    Gets the application's root directory.

    For development (non-frozen) environments, it robustly finds the project root
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


def get_all_baked_json(table_name: str) -> Dict[str, Dict[str, Any]]:
    """
    Finds, reads, and parses all .json files from a specified directory
    within 'src/utils/baked/'.

    This function works correctly whether the application is running from source
    or as a frozen executable created by PyInstaller.

    Args:
        table_name: The name of the directory inside 'src/utils/baked/' to scan for JSON files.

    Returns:
        A list of parsed JSON objects (as dictionaries).

    Raises:
        FileNotFoundError: If the specified directory for the table_name does not exist.
    """
    is_frozen = getattr(sys, 'frozen', False)

    if is_frozen:
        # In a frozen app, data is in the _MEIPASS temp directory.
        # The path is relative to what was defined in the .spec file's `datas` tuple.
        # e.g., datas=[('src/utils/baked', 'utils/baked')]
        base_path = Path(sys._MEIPASS)
        # The 'src' part is dropped, so we use the destination path directly.
        data_dir = base_path / 'utils' / 'baked' / table_name
    else:
        # In a development environment, use get_application_path to find project root.
        base_path = Path(get_application_path())
        # The path from project root includes 'src'.
        data_dir = base_path / 'src' / 'utils' / 'baked' / table_name

    if not data_dir.is_dir():
        raise FileNotFoundError(
            f"The data directory for table '{table_name}' was not found at expected path: {data_dir}"
        )

    parsed_json_files = {}
    for file_path in data_dir.glob('*.json'):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                parsed_json_files[file_path] = json.load(f)
        except json.JSONDecodeError as e:
            print(f"Warning: Could not parse {file_path}. Error: {e}")
        except Exception as e:
            print(f"Warning: An unexpected error occurred while reading {file_path}. Error: {e}")

    return parsed_json_files

# --- Example Usage ---

# Imagine your directory structure is:
# src/
# └── utils/
#     └── baked/
#         ├── users/
#         │   ├── user1.json
#         │   └── user2.json
#         └── products/
#             ├── productA.json
#             └── productB.json

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
