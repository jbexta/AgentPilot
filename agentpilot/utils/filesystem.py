import os
import sys


def get_application_path():
    if sys.platform == 'win32':
        print("sys.executable:", sys.executable)
        return os.path.dirname(os.path.abspath(sys.executable))
    elif sys.platform == 'linux':
        app_image_var = os.environ.get('APPIMAGE')
        if not app_image_var:
            raise NotImplementedError()
        return os.path.dirname(app_image_var)
    elif sys.platform == 'darwin':  # Mac OS
        print("sys.executable:", sys.executable)
        print("dirname of os.path.abspath(sys.executable):", os.path.dirname(os.path.abspath(sys.executable)))
        return os.path.dirname(os.path.abspath(sys.executable))
