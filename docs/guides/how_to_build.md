# How to build

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
pyinstaller --onefile --add-data 'agentpilot/plugins:agentpilot/plugins' --hidden-import=tiktoken_ext.openai_public --hidden-import=tiktoken_ext agentpilot/__main__.py
```

This will create a `dist` folder in the project root directory. The executable will be in the `dist` folder.

### Copy the database, config file and avatars to the dist folder

```bash
cp data.db dist/data.db
cp configuration.yaml dist/configuration.yaml
cp -r docs/avatars dist/avatars
```

### Test the executable

```bash
./dist/__main__
```

To make the executable compatible with other linux systems, you can exclude system libraries from the build.
<br>Edit the .spec file generated from pyinstaller and add the following, right after the `a = Analysis(...)` line:

```bash
a = Analysis(
  ...
)
excluded_libs = ['libstdc++.so', 'iris_dri.so', 'swrast_dri.so']
a.binaries = [(pkg, src, typ) for pkg, src, typ in a.binaries
              if not any(lib in src for lib in excluded_libs)]
```

### Create an appimage

...