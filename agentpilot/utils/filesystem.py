import os
import sys


def get_application_path():
    if sys.platform == 'win32':
        # print("sys.executable:", sys.executable)
        return os.path.dirname(os.path.abspath(sys.executable))
    elif sys.platform == 'linux':
        # print(os.environ.get('APPIMAGE'))
        # print other possible executable paths
        # print("sys.executable:", sys.executable)
        # print("dirname of os.path.abspath(sys.executable):", os.path.dirname(os.path.abspath(sys.executable)))
        # print("dirname of os.path.abspath(__file__):", os.path.dirname(os.path.abspath(__file__)))
        # print("dirname of os.path.abspath(os.path.dirname(__file__)):", os.path.dirname(os.path.abspath(os.path.dirname(__file__))))
        app_image_var = os.environ.get('APPIMAGE')
        if not app_image_var:
            app_image_var = os.path.abspath(sys.executable)
        return os.path.dirname(app_image_var)
    elif sys.platform == 'darwin':  # Mac OS
        # print("sys.executable:", sys.executable)
        # print("dirname of os.path.abspath(sys.executable):", os.path.dirname(os.path.abspath(sys.executable)))
        return os.path.dirname(os.path.abspath(sys.executable))


def unsimplify_path(path):
    from agentpilot.utils import filesystem
    exe_dir = filesystem.get_application_path()
    print("EXE DIR: ", exe_dir)

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

    print("UNSIMP: ", abs_path)
    return abs_path  # os.path.abspath(abs_path)  # return absolute path


def simplify_path(path):
    from agentpilot.utils import filesystem
    abs_path = os.path.abspath(path)
    exe_dir = filesystem.get_application_path()

    if abs_path.startswith(exe_dir):
        rel_path = os.path.relpath(abs_path, exe_dir)
        return '.' + os.sep + rel_path
    else:
        return abs_path