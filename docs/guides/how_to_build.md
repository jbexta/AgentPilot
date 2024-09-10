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

```bash
python build.py
```

### Test the executable

```bash
./dist/__main__
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