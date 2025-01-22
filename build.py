# !/usr/bin/env python3.10

import os
import platform
import subprocess
import shutil
import sys
# import venv
import argparse


def parse_arguments():
    parser = argparse.ArgumentParser(description="Build script for AgentPilot")
    parser.add_argument('--skip-venv', action='store_true', help='Skip creating a new virtual environment')
    return parser.parse_args()


# def get_pyenv_path():
#     return os.path.join(os.environ["PYENV_ROOT"], "versions", 'apbuildvenv')

def get_version_from_pyproject_toml():
    with open("pyproject.toml") as f:
        for line in f:
            if "version" in line:
                return line.split("=")[1].strip().replace('"', '')
    return "0.1.0"


def run_command(command, shell=False, env=None):
    if isinstance(command, str):
        command = command.split()
    print(f"Running command: {' '.join(command)}")
    if env:
        print(f"Environment: {env}")

    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=shell, env=env)
    output, error = process.communicate()
    if process.returncode != 0:
        print(f"Error executing command: {' '.join(command)}")
        print(f"Output: {output.decode()}")
        print(f"Error: {error.decode()}")
        exit(1)
    return output.decode()


class Builder:
    def __init__(self):
        os.chdir(os.path.dirname(os.path.abspath(__file__)))
        self.args = parse_arguments()
        self.platform = platform.system()
        self.version = get_version_from_pyproject_toml()

        if self.platform == "Linux":
            self.venv_path = os.path.join(os.environ["PYENV_ROOT"], "versions", 'apbuildvenv')
        elif self.platform == "Windows":
            self.venv_path = os.environ.get("PYENV_ROOT", os.path.join(os.environ["USERPROFILE"], ".pyenv")) + "\\versions\\apbuildvenv"
        elif self.platform == "Darwin":
            try:
                self.venv_path = f'{run_command("pyenv root").strip()}/versions/apbuildvenv'
            except Exception as e:
                raise Exception("pyenv not found. Please install pyenv and pyenv-virtualenv")

        self.pip_path = self.get_pip_path()
        self.pyinstaller_path = self.get_pyinstaller_path()

    def get_pip_path(self):
        if self.platform == "Windows":
            return os.path.join(self.venv_path, "Scripts", "pip")
        else:
            return os.path.join(self.venv_path, "bin", "pip")

    def get_pyinstaller_path(self):
        if self.platform == "Windows":
            return os.path.join(self.venv_path, "Scripts", "pyinstaller.exe")
        else:
            return os.path.join(self.venv_path, "bin", "pyinstaller")

    def create_executable(self):
        self.setup_environment()
        self.install_requirements()
        self.build_project()
        self.copy_assets()

        if self.platform == "Windows":
            self.rename_executable()
        elif self.platform == "Linux":
            self.make_appimage()

        self.move_all_to_folder()
        self.compress_app()

    def setup_environment(self):
        if self.args.skip_venv:
            return

        output = run_command("pyenv virtualenvs --bare")
        venvs = output.splitlines()
        env_exists = 'apbuildvenv' in venvs
        if env_exists:
            run_command("pyenv virtualenv-delete -f apbuildvenv")

        print("Creating new pyenv virtual environment..")
        run_command("pyenv virtualenv 3.10.11 apbuildvenv")

    def install_requirements(self):
        run_command([self.pip_path, "install", "-r", "requirements.txt"])

    def build_project(self):
        print("Installing PyInstaller..")
        run_command([self.pip_path, "install", "pyinstaller"])

        print("Building executable..")
        run_command([self.pyinstaller_path, "build.spec"])

    def copy_assets(self):
        shutil.copy("data.db", "dist/data.db")
        shutil.copytree("docs/avatars", "dist/avatars", dirs_exist_ok=True)

    def rename_executable(self):
        old_filename = "__main__"
        new_filename = f"AgentPilot_{self.version}"
        if self.platform == "Windows":
            os.rename(f"dist/{old_filename}.exe", f"dist/{new_filename}.exe")
        else:
            os.rename(f"dist/{old_filename}", f"dist/{new_filename}")

    def move_all_to_folder(self):
        folder_name = f"AgentPilot_{self.version}_{self.platform}_Portable"

        if os.path.exists(f'dist/{folder_name}'):
            shutil.rmtree(f'dist/{folder_name}')
        os.mkdir(f'dist/{folder_name}')

        # move all files to folder
        ignore_exts = ['zip', 'tar.gz']
        for file in os.listdir("dist"):
            if file != folder_name and not any(file.endswith(e) for e in ignore_exts):
                shutil.move(f"dist/{file}", f"dist/{folder_name}/{file}")

    def make_appimage(self):
        # Create AppDir folder
        if os.path.exists("AppDir"):
            shutil.rmtree("AppDir")
        os.mkdir("AppDir")

        # make AppDir/usr/bin
        os.makedirs("AppDir/usr/bin")

        # create agentpilot.desktop
        with open("AppDir/agentpilot.desktop", "w") as f:
            f.write("""[Desktop Entry]
Type=Application
Name=AgentPilot
Comment=Build and chat with agents
Exec=usr/bin/main
Icon=icon
Terminal=false
Categories=Utility;""")

        # create AppRun link
        with open("AppDir/AppRun", "w") as f:
            f.write('''#!/bin/sh
HERE=$(dirname "$(readlink -f "${0}")")
export PATH="${HERE}/usr/bin:$PATH"
exec main "$@"''')
        os.chmod("AppDir/AppRun", 0o755)

        # copy icon
        shutil.copy("src/utils/resources/icon.png", "AppDir/icon.png")
        shutil.copy("src/utils/resources/icon.png", "AppDir/.DirIcon")

        # copy executable
        shutil.copy(f"dist/AgentPilot", "AppDir/usr/bin/main")

        # check if appimagetool file exists
        if not os.path.exists("appimagetool.AppImage"):
            print("AppImageTool not found. Downloading..")
            run_command("wget -c https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage")
            os.rename("appimagetool-x86_64.AppImage", "appimagetool.AppImage")

        # make appimage with appimagetool
        run_command("chmod +x appimagetool.AppImage")
        run_command("./appimagetool.AppImage AppDir")

        # rename appimage and move to the folder
        os.rename("AgentPilot-x86_64.AppImage", f"dist/AgentPilot_{self.version}.AppImage")

        # remove the original executable
        os.remove(f"dist/AgentPilot")

    def compress_app(self):
        source_folder = f"dist/AgentPilot_{self.version}_{self.platform}_Portable"
        output_filename = f"dist/AgentPilot_{self.version}_{self.platform}_Portable"

        base_name = os.path.basename(source_folder)
        base_dir = os.path.dirname(source_folder)

        ext = "zip" if self.platform == "Windows" else "tar.gz"
        if os.path.exists(f"{output_filename}.{ext}"):
            os.remove(f"{output_filename}.{ext}")

        if self.platform == "Windows":
            shutil.make_archive(
                base_name=output_filename,
                format="zip",
                root_dir=base_dir,
                base_dir=base_name
            )
        else:
            shutil.make_archive(
                base_name=output_filename,
                format="gztar",
                root_dir=base_dir,
                base_dir=base_name
            )


if __name__ == "__main__":
    builder = Builder()
    builder.create_executable()
