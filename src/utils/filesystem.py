import logging
import os
import sys


# def get_application_path():
#     if getattr(sys, 'frozen', True):
#         return os.path.abspath(os.path.join(os.path.dirname(__file__), os.path.pardir, os.path.pardir))
#
#     if sys.platform == 'win32':
#         return os.path.dirname(os.path.abspath(sys.executable))
#     elif sys.platform == 'linux':
#         app_image_var = os.environ.get('APPIMAGE')
#         if not app_image_var:
#             app_image_var = os.path.abspath(sys.executable)
#         return os.path.dirname(app_image_var)
#     elif sys.platform == 'darwin':  # Mac OS todo test
#         return os.path.dirname(os.path.abspath(sys.executable))

def get_application_path():
    if sys.platform == 'win32':
        if getattr(sys, 'frozen', False):
            return os.path.dirname(sys.executable)

        return os.path.abspath(os.path.dirname(os.path.dirname(os.path.dirname(sys.executable))))

    elif sys.platform == 'linux':
        is_in_exe = getattr(sys, 'frozen', False)
        if is_in_exe:
            return os.path.dirname(os.environ.get('APPIMAGE'))

        return f"{os.path.abspath(__file__).split('AgentPilot')[0]}AgentPilot"

    elif sys.platform == 'darwin':  # Mac OS todo test
        return os.path.dirname(os.path.abspath(sys.executable))


def unsimplify_path(path):
    exe_dir = get_application_path()

    if 'OPENAI_API_KEY' in os.environ.keys():
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
