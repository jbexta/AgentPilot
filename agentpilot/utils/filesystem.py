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
