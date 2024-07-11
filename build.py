import os
import platform
import subprocess
import shutil
import sys
import venv


def run_command(command, shell=False, env=None):
    if isinstance(command, str):
        command = command.split()
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=shell, env=env)
    output, error = process.communicate()
    if process.returncode != 0:
        print(f"Error executing command: {' '.join(command)}")
        print(error.decode())
        exit(1)
    return output.decode()


def get_pip_path(venv_path):
    if platform.system() == "Windows":
        return os.path.join(venv_path, "Scripts", "pip")
    else:
        return os.path.join(venv_path, "bin", "pip")


def setup_environment():
    venv_path = os.path.join(os.getcwd(), "agentpilotvenv")

    # env_exists = os.path.exists(venv_path)
    # if env_exists:
    #     print("Virtual environment already exists, deleting it..")
    #     shutil.rmtree(venv_path)
    #
    # print("Creating new virtual environment..")
    # venv.create(venv_path, with_pip=True)

    return venv_path


def activate_venv(venv_path):
    if platform.system() == "Windows":
        activate_script = os.path.join(venv_path, "Scripts", "activate")
    else:
        activate_script = os.path.join(venv_path, "bin", "activate")

    if not os.path.exists(activate_script):
        print(f"Activation script not found: {activate_script}")
        sys.exit(1)

    # Modify the PATH to prioritize the virtual environment
    os.environ["PATH"] = os.pathsep.join([
        os.path.join(venv_path, "bin"),
        os.environ.get("PATH", "")
    ])

    # Modify VIRTUAL_ENV environment variable
    os.environ["VIRTUAL_ENV"] = venv_path

    # Remove PYTHONHOME if set
    os.environ.pop("PYTHONHOME", None)


def install_requirements(venv_path):
    pip_path = get_pip_path(venv_path)
    run_command([pip_path, "install", "-r", "requirements.txt"])


def build_project(venv_path):
    pip_path = get_pip_path(venv_path)

    print("Installing PyInstaller..")
    run_command([pip_path, "install", "pyinstaller"])

    print("Building executable..")
    run_command(["pyinstaller", "build.spec"])


def copy_assets():
    shutil.copy("data.db", "dist/data.db")
    shutil.copytree("docs/avatars", "dist/avatars", dirs_exist_ok=True)


def rename_executable():
    pf = platform.system()
    old_filename = "__main__"
    new_filename = "AgentPilot_0.3.0"  # _{pf}_Portable"
    if pf == "Windows":
        os.rename(f"dist/{old_filename}.exe", f"dist/{new_filename}.exe")
    else:
        os.rename(f"dist/{old_filename}", f"dist/{new_filename}")


def compress_app():
    pf = platform.system()
    if pf == "Windows":
        shutil.make_archive("dist", "zip", "dist")
    else:
        shutil.make_archive("dist", "tar", "dist")


def main():
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    print("Setting up environment..")
    venv_path = setup_environment()

    print("Activating virtual environment..")
    activate_venv(venv_path)

    print("Installing requirements..")
    install_requirements(venv_path)

    print("Building project...")
    build_project(venv_path)

    print("Copying assets...")
    copy_assets()

    print("Finishing up..")
    rename_executable()
    compress_app()

    print("Build complete. Executable is in the 'dist' folder.")


if __name__ == "__main__":
    main()
