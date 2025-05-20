import os
import platform
import subprocess
from typing_extensions import override

from src.utils.filesystem import get_application_path
from src.utils.helpers import ManagerController


class VenvManager(ManagerController):
    def __init__(self, parent, table_name=None):
        super().__init__(parent)

    @override
    def load(self):
        venv_folder = os.path.join(get_application_path(), "venvs")
        if not os.path.exists(venv_folder):
            return

        del_keys = list(self.keys())
        for venv_name in os.listdir(venv_folder):
            if venv_name not in self:
                self[venv_name] = self.Venv(venv_name)
            if venv_name in del_keys:
                del_keys.remove(venv_name)

        for key in del_keys:
            del self[key]

    @override
    def add(self, name, **kwargs):
        venv_folder = os.path.join(get_application_path(), "venvs")
        if not os.path.exists(venv_folder):
            os.makedirs(venv_folder)

        venv_path = os.path.join(get_application_path(), "venvs", name)
        if os.path.exists(venv_path):
            raise ValueError(f"Virtual environment {name} already exists.")

        print(f"Creating virtual environment {name}...")
        try:
            # use pyenv to create the virtual environment, cross-platform
            # making sure its installed, if not, install it
            if platform.system() == "Windows":
                # powershell Invoke-WebRequest -UseBasicParsing -Uri "https://raw.githubusercontent.com/pyenv-win/pyenv-win/master/pyenv-win/install-pyenv-win.ps1" -OutFile "./install-pyenv-win.ps1"; &"./install-pyenv-win.ps1"
                run_command(["Invoke-WebRequest", "-UseBasicParsing", "-Uri", "https://raw.githubusercontent.com/pyenv-win/pyenv-win/master/pyenv-win/install-pyenv-win.ps1", "-OutFile", "./install-pyenv-win.ps1"])
            else:
                # run the command:  `python3 -m venv {venv_path}`
                run_command(["python3", "-m", "venv", venv_path])


            # venv.create(venv_path, with_pip=True, system_site_packages=True)

            # # install pip manually using run_command
            # python_path = get_python_path(venv_path)
            # run_command([python_path, "-m", "ensurepip", "upgrade", "default-pip"])

            # # Ensure pip is installed and up to date
            # python_path = get_python_path(venv_path)
            # # subprocess.check_call([python_path, "-m", "ensurepip", "--upgrade"])
            # # subprocess.check_call([python_path, "-m", "pip", "install", "--upgrade", "pip"])
            #
            # #####
            # run_command([python_path, "-m", "ensurepip", "upgrade", "default-pip"])
            # # This doesnt work, are the "-" needed? The answer is no, they are not needed.
            print(f"Virtual environment {name} created successfully.")
        except Exception as e:
            raise ValueError(f"Error creating virtual environment: {str(e)}")

        self.load()

    @override
    def delete(self, key, where_field='id'):
        if key not in self:
            return

        print(f"Deleting virtual environment {key}...")
        try:
            venv_path = self[key].path
            print(run_command(f"rm -rf {venv_path}"))

            # print(f"Virtual environment {name} deleted successfully.")
        except Exception as e:
            raise ValueError(f"Error deleting virtual environment: {str(e)}")

        self.load()

    class Venv:
        def __init__(self, name):
            self.name = name
            self.path = os.path.join(get_application_path(), "venvs", name)  # path is in app_path/venvs/name
            self.python_path = os.path.join(get_application_path(), "venvs", name, "bin", "python")
            self.pip_path = get_pip_path(self.path)

        def install_package(self, package):
            """
            Installs a package into the virtual environment.
            """
            run_command([self.pip_path, "install", package])

        def uninstall_package(self, package):
            """
            Uninstalls a package from the virtual environment.
            """
            run_command([self.pip_path, "uninstall", package])

        def list_packages(self):
            """
            Lists all installed packages in the virtual environment.
            """
            python_exists = os.path.exists(self.python_path)
            pip_exists = os.path.exists(self.pip_path)
            if not python_exists or not pip_exists:
                return []

            packages = run_command([self.python_path, self.pip_path, "list"])
            packages = [package.split() for package in packages.split("\n")[2:-1]]
            print(packages)
            return packages

        def has_package(self, package):
            """
            Checks if a package is installed in the virtual environment.
            """
            packages = self.list_packages()
            return any(package in package_info for package_info in packages)


        # def delete(self):
        #     """
        #     Deletes the virtual environment.
        #     """
        #     run_command(f"rm -rf {self.path}")


# def get_application_path():
#     if getattr(sys, 'frozen', True):
#         return os.path.abspath(os.path.join(os.path.dirname(__file__), os.path.pardir, os.path.pardir))
#
#     if platform.system() == "Windows":
#         return os.path.dirname(os.path.abspath(sys.executable))
#     elif platform.system() == "Linux":
#         app_image_var = os.environ.get('APPIMAGE')
#         if not app_image_var:
#             app_image_var = os.path.abspath(sys.executable)
#         return os.path.dirname(app_image_var)
#     elif platform.system() == "Darwin":
#         return os.path.dirname(os.path.abspath(sys.executable))


def get_pip_path(venv_path):
    if platform.system() == "Windows":
        return os.path.join(venv_path, "Scripts", "pip")
    else:
        return os.path.join(venv_path, "bin", "pip")


def get_python_path(venv_path):
    if platform.system() == "Windows":
        return os.path.join(venv_path, "Scripts", "python.exe")
    else:
        return os.path.join(venv_path, "bin", "python")


def run_command(command, shell=False, env=None):
    try:
        result = subprocess.run(command, shell=shell, env=env, check=True, capture_output=True, text=True)
        output = result.stdout
    except subprocess.CalledProcessError as e:
        output = e.stdout + "\n" + e.stderr
    return output
