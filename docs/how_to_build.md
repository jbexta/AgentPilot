# How to build

## Linux

### Clone the repo
    
```bash
git clone https://github.com/jbexta/AgentPilot.git
```

### CD to the project

```bash
cd AgentPilot
```

### Run the build script
_This requires pyenv to be installed on your system_
```bash
python3 build.py
```

### Test the executable

```bash
./dist/AgentPilot_0.5.1_Linux/AgentPilot_0.5.1.AppImage
```

# How to build without build script

## Linux

### CD to where you want to clone the project

```bash
cd ~/PycharmProjects
```

### Clone the repo
    
```bash
git clone https://github.com/jbexta/AgentPilot.git
```

### CD to the project

```bash
cd AgentPilot
```


### Activate a 3.10.11 virtual environment (I'm using pyenv)

```bash
pyenv install 3.10.11
pyenv virtualenv 3.10.11 agentpilotvenv
pyenv activate agentpilotvenv
```


### Install dependencies

```bash
pip install -r requirements.txt
```

### Install pyinstaller

```bash
pip install pyinstaller
```

### Build the project

```bash
pyinstaller build.spec
```

This will create a `dist` folder in the project root directory. The executable will be in the `dist` folder.

### Copy the database and avatars to the dist folder

```bash
cp data.db dist/data.db
cp -r docs/avatars dist/avatars
```

### Test the executable

```bash
./dist/__main__
```

### Create an appimage

...

# How to build for Android

Android packaging is a **cross-compile**: a Linux or macOS host produces an
Android `.apk` (debug) or `.aab` (release) using PySide6's official toolchain
(`pyside6-android-deploy` → buildozer → python-for-android). It does not run on
a Windows host.

## Prerequisites

- A Linux or macOS host.
- Python 3.11 (must match the `cp311` tag of the PySide6 Android wheels).
- A JDK on `PATH` (`java`/`javac`), e.g. `sudo apt install openjdk-17-jdk`.
- Android SDK + NDK. Either set `ANDROID_SDK_ROOT` / `ANDROID_NDK_HOME` to
  existing installs, or let buildozer download them on first run.
- PySide6 + shiboken6 **Android** wheels for your target architecture. These are
  **not on PyPI** — download them from <https://download.qt.io/> (under the
  matching Qt for Python release). The wheel names look like
  `PySide6-6.8.3-cp311-cp311-android_aarch64.whl` and
  `shiboken6-6.8.3-cp311-cp311-android_aarch64.whl`.

## Run the build script

```bash
# Drop the two Android wheels in ./android_wheels/ (auto-discovered)...
python3 build_android.py --arch aarch64 --mode debug

# ...or point at them explicitly:
python3 build_android.py \
    --wheel-pyside  /path/to/PySide6-...-android_aarch64.whl \
    --wheel-shiboken /path/to/shiboken6-...-android_aarch64.whl
```

- `--arch` — `aarch64` (default), `armv7a`, `i686`, or `x86_64`.
- `--mode` — `debug` (produces `.apk`) or `release` (produces `.aab`).
- `--init` — only (re)generate the working spec and exit (no SDK/NDK needed).

The script copies the tracked template `pysidedeploy_android.spec` into a
gitignored working copy `pysidedeploy_android.local.spec`, fills in the
machine-local paths, and invokes `pyside6-android-deploy`. The resulting package
is moved to `AgentPilot_<version>_<arch>.{apk,aab}` in the repo root.

## Limitations

python-for-android can only bundle pure-Python packages and packages that have a
p4a recipe. Several desktop plugins depend on native libraries with no Android
support (`pyautogui`, `playwright`, `docker`, `h5py`, `psycopg2`,
`mysql-connector`, `av`/`moviepy`, …) and cannot be included. This script sets up
and drives the build; trimming the runtime import graph so the app actually
links and launches on-device is follow-up work tracked separately.