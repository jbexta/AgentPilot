import os
import sys


def get_application_path():
    if sys.platform == 'win32':
        return os.path.dirname(os.path.abspath(sys.executable))
    elif sys.platform == 'linux':
        return os.path.dirname(os.environ.get('APPIMAGE'))
    elif sys.platform == 'darwin':  # Mac OS
        return os.path.dirname(os.path.abspath(sys.executable))
