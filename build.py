#!/usr/bin/env python3.10

import os
import platform
import subprocess
import shutil
import sys
import venv
import argparse

def parse_arguments():
    parser = argparse.ArgumentParser(description="Build script for AgentPilot")
    parser.add_argument('--skip-venv', action='store_true', help='Skip creating a new virtual environment')
    parser.add_argument('--version', type=str, default='0.3.0', help='Version number for the build')
    return parser.parse_args()


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


def setup_environment(skip_venv=False):
    venv_path = os.path.join(os.getcwd(), "buildvenv")

    if not skip_venv:
        env_exists = os.path.exists(venv_path)
        if env_exists:
            print("Virtual environment already exists, deleting it..")
            shutil.rmtree(venv_path)

        print("Creating new virtual environment..")
        venv.create(venv_path, with_pip=True)

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


def rename_executable(version):
    pf = platform.system()
    old_filename = "__main__"
    new_filename = "AgentPilot_0.3.0"  # _{pf}_Portable"
    if pf == "Windows":
        os.rename(f"dist/{old_filename}.exe", f"dist/{new_filename}.exe")
    else:
        os.rename(f"dist/{old_filename}", f"dist/{new_filename}")


def move_all_to_folder(version):
    pf = platform.system()
    folder_name = f"AgentPilot_0.3.0_{pf}_Portable"

    if os.path.exists(f'dist/{folder_name}'):
        shutil.rmtree(f'dist/{folder_name}')
    os.mkdir(f'dist/{folder_name}')

    # move all files to folder
    ignore_exts = ['zip', 'tar.gz']
    for file in os.listdir("dist"):
        if file != folder_name and not any(file.endswith(e) for e in ignore_exts):
            shutil.move(f"dist/{file}", f"dist/{folder_name}/{file}")


def compress_app(version):
    pf = platform.system()
    source_folder = f"dist/AgentPilot_0.3.0_{pf}_Portable"
    output_filename = f"dist/AgentPilot_0.3.0_{pf}_Portable"

    base_name = os.path.basename(source_folder)
    base_dir = os.path.dirname(source_folder)

    ext = "zip" if pf == "Windows" else "tar.gz"
    if os.path.exists(f"{output_filename}.{ext}"):
        os.remove(f"{output_filename}.{ext}")

    if pf == "Windows":
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


def main():
    args = parse_arguments()

    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    print("Setting up environment..")
    venv_path = setup_environment(skip_venv=args.skip_venv)

    print("Activating virtual environment..")
    activate_venv(venv_path)

    print("Installing requirements..")
    install_requirements(venv_path)

    print("Building project...")
    build_project(venv_path)

    print("Copying assets...")
    copy_assets()

    print("Finishing up..")
    rename_executable(args.version)
    move_all_to_folder(args.version)
    compress_app(args.version)

    print("Build complete. Executable is in the 'dist' folder.")


if __name__ == "__main__":
    main()
