# Contents
- [Creating an agent plugin](#creating-an-agent-plugin)
  - [Create a directory under `src/plugins` to store your plugin](#create-a-directory-under-srcplugins-to-store-your-plugin)
  - [Inside `agent_plugin.py`](#inside-agent_pluginpy)
    - [Import the Agent base class](#import-the-agent-base-class)
    - [Create a class that inherits from Agent](#create-a-class-that-inherits-from-agent)
    - [Overridable methods](#overridable-methods)
    - [Overridable attributes](#overridable-attributes)
    - [Creating a custom GUI config widget for the agent](#creating-a-custom-gui-config-widget-for-the-agent)
    - [Creating instance parameters](#creating-instance-parameters)
    - [Example](#example)
- [Creating a workflow plugin](#creating-a-context-plugin)
  - [Create a directory under `src/plugins` to store your plugin](#create-a-directory-under-srcplugins-to-store-your-plugin-1)
  - [Inside `workflow_plugin.py`](#inside-workflow_pluginpy)
    - [Import the Context base class](#import-the-context-base-class)
    - [Create a class that inherits from Context](#create-a-class-that-inherits-from-context)
    - [Overridable methods](#overridable-methods-1)
    - [Overridable attributes](#overridable-attributes-1)
    - [Creating extra parameters](#creating-extra-parameters-1)
    - [Creating instance parameters](#creating-instance-parameters-1)
    - [Example:](#example-1)

# Creating an agent plugin

Agent plugins can be created to override the native agent behavior, extend functionality & modify the GUI config widget when the plugin is used.<br>

## Create a directory under `src/plugins` to store your plugin

Inside the directory:
- Create a folder named `modules`
- Create a folder called `src` if you want to include any source code
- Create a file called `__init__.py` in all new folders so they're recognized by python
- Create a file called `agent_plugin.py` in the `modules` folder

Your directory structure should look like this:

```bash
agentpilot
├── ...
├── plugins
│   ├── __init__.py
│   └── my_plugin
│       ├── __init__.py
│       └── modules
│           ├── __init__.py
│           └── agent_plugin.py
├── ...
```

## Inside `agent_plugin.py`:

### Import the Agent base class

```python
from src.members.agent import Agent
```

### Create a class that inherits from Agent

```python
from src.members.agent import Agent
from src.plugins.my_plugin.src.core import MyExternalAgent

class My_Plugin(Agent):  # The app will use this class name in the plugin dropdown menu.
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.agent_object = None

    def load(self):
        """
        Any custom loading code here, called when a chat with this agent is loaded.
        Make sure to call super().load() to load the base agent.
        """
        super().load()
        self.agent_object = MyExternalAgent()

    def stream(self):
        """Generator method that streams (yields) a tuple of (role, chunk)"""
        messages = self.workflow.message_history.get(llm_format=True, calling_member_id=self.member_id)
        for chunk in self.agent_object.chat(message=messages):
            yield 'assistant', chunk
```

Now from your agent plugin class, you can override methods and access the base attributes by using `self` or `super()`.

### Base agent methods
- <b>stream()</b> - This generator function is used for streaming a response. It must yield a tuple of (role, chunk). 
<br>If streaming isn't possible then just yield the entire response as a single chunk.
- <b>load()</b> - This method is called when the plugin is loaded. If overriding this method, make sure to call `super().load()` to load the base agent.
- <b>system_message()</b> - This function is used to retrieve the system message for the agent. It can be overridden to return a custom system message. You can access the default system message by using `super().system_message()`.

### Base agent attributes
- <b>self.workflow</b> - Using this you can access all methods and attributes of the current `Workflow`.

### Register the plugin in `src/system/plugins.py`
In the `src/system/plugins.py` file, import the plugin and add it to the `ALL_PLUGINS` dictionary.
```python
from src.plugins.myplugin.modules.agent_plugin import My_Plugin, MyPluginSettings

ALL_PLUGINS = {
    'Agent': [
        Open_Interpreter,
        OpenAI_Assistant,
        My_Plugin  # Add your custom agent class here
    ],
    'AgentSettings': {  # The key must match the agent class name
        'Open_Interpreter': OpenInterpreterSettings,
        'OpenAI_Assistant': OAIAssistantSettings,
        'My_Plugin': MyPluginSettings,  # Add your custom agent config class here
    },
}
```

### Creating a custom GUI config widget for the agent
You can completely customise the pages, tabs and parameters of the default agent config. <br>
The GUI will automatically create the pages, tabs, trees and fields. <br>

To do this, create a class that inherits from `AgentSettings` and register it in `src/system/plugins.py`.<br>

`AgentSettings` is the default agent settings class, it is composed of multiple `ConfigWidgets` that can be connected or nested together.<br>

Types of `ConfigWidgets`:
- `ConfigFields` - A list of parameters, see below for available types.
- `ConfigTabs` - A collection of tabs, represented as a dictionary of `ConfigWidgets` with the tab name as the key.
- `ConfigPages` - A collection of pages, represented as a dictionary of `ConfigWidgets` with the page name as the key.
- `ConfigJoined` - A list of `ConfigWidgets` that will be joined either vertically or horizontally.
- `ConfigDBTree` - A tree of items from the db, with an optional config widget shown either below or to the right of the tree,
- `ConfigJsonTree` - A tree of items that are saved to and loaded from json in the config.

### ConfigFields
`ConfigFields` has a `schema` attribute that is a list of dictionaries, each representing a parameter.

*Example of a `str` parameter:*
```python
self.schema = [
    {
        'text': 'System message',
        'key': 'sys_msg',
        'type': str,
        'num_lines': 10,
        'default': '',
        'width': 535,
        'label_position': 'top',
    },
    ...
]
```

Available types:
- `str` - Text field
- `bool` - Checkbox
- `int` - Numeric
- `float` - Numeric
- `tuple` - Combobox (This should be an instance of a tuple, not the type)
- `ModelComboBox` - LLM model combobox (This should be a string)

Each parameter dict can contain the following keys:
- `type` - Type of the parameter from the above list
- `text` - Text to display for the label
- `key` - The key to use in `self.config` (Optional, defaults to `text.lower().replace(' ', '_')`)
- `default` - Default value of the parameter
- `width` - Width of the widget (Optional)
- `row_key` - Row key of the widget, if matches the previous item row key, they will share the same row (Optional)
- `label_width` - Width of the label (Optional)
- `label_position` - Position of the label relative to the widget (Optional, defaults to 'left')
- `text_alignment` - Text alignment of the widget (Optional, defaults to 'left')
- `text_size` - Size of the text in the GUI (Optional)
- `num_lines` - Number of lines for a *str* type (Optional, defaults to 1)
- `minimum` - Minimum value for *int* or *float* types (Optional, defaults to 0)
- `maximum` - Maximum value for *int* or *float* types (Optional, defaults to 1)
- `step` - The step value for *int* or *float* types (Optional, defaults to 1)
- `has_toggle` - If True, the widget will have a toggle button (Optional, defaults to False)
- `tooltip` - Tooltip text to display when hovering over the widget (Optional)

### ConfigTabs & ConfigPages
`ConfigTabs` and `ConfigPages` have a `pages` attribute that is a dictionary of `ConfigWidgets` with the tab/page name as the key.

### Example

```python
from src.members.agent import AgentSettings, Agent
from src.plugins.openinterpreter.src import OpenInterpreter
from src.gui.config import ConfigFields, ConfigTabs, ConfigJoined, ConfigJsonTree

class My_Plugin(Agent):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        ...

    def load(self):
        ...

    async def stream(self, *args, **kwargs):
      ...

    def convert_messages(self, messages):
      ...


class MyPluginSettings(AgentSettings):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        """
        The super class `AgentSettings(ConfigPages)` are the default settings.
        We can modify this to suit the plugin.
        """
        # Remove any tabs you don't want
        self.pages.pop('Files')
        
        # Change the `Messages` tab schema
        self.pages['Chat'].pages['Messages'].schema = [
            {
                'text': 'Model',
                'type': 'ModelComboBox',
                'default': 'mistral/mistral-large-latest',
                'row_key': 0,
            },
            {
                'text': 'Display markdown',
                'type': bool,
                'default': True,
                'row_key': 0,
            },
            {
                'text': 'System message',
                'key': 'sys_msg',
                'type': str,
                'num_lines': 10,
                'default': '',
                'stretch_x': True,
                'label_position': 'top',
            },
            {
                'text': 'Max messages',
                'type': int,
                'minimum': 1,
                'maximum': 99,
                'default': 10,
                'width': 60,
                'has_toggle': True,
                'row_key': 1,
            },
            {
                'text': 'Max turns',
                'type': int,
                'minimum': 1,
                'maximum': 99,
                'default': 7,
                'width': 60,
                'has_toggle': True,
                'row_key': 1,
            },
            {
                'text': 'Custom instructions',
                'type': str,
                'num_lines': 2,
                'default': '',
                'width': 260,
                'label_position': 'top',
                'row_key': 2,
            },
            {
                'text': 'User message template',
                'type': str,
                'num_lines': 2,
                'default': '{content}',
                'width': 260,
                'label_position': 'top',
                'row_key': 2,
            },
        ]
        
        # The `Info` tab is a `ConfigJoined` widget, so we can join another config widget to it.
        info_widget = self.pages['Info']
        info_widget.widgets.append(self.Plugin_Fields(parent=info_widget))

        # Add more pages
        self.pages['New page name'] = self.MyConfigWidget(parent=self)

    class Plugin_Fields(ConfigFields):
        def __init__(self, parent):
            super().__init__(parent=parent)
            self.parent = parent
            self.conf_namespace = 'plugin'
            self.label_width = 150
            self.schema = [
                {
                    'text': 'Offline',
                    'type': bool,
                    'default': False,
                    'map_to': 'offline',
                },
                {
                    'text': 'Safe mode',
                    'type': ('off', 'ask', 'auto',),
                    'default': False,
                    'map_to': 'safe_mode',
                    'width': 75,
                },
                {
                    'text': 'Disable telemetry',
                    'type': bool,
                    'default': False,
                    'map_to': 'disable_telemetry',
                },
                {
                    'text': 'OS',
                    'type': bool,
                    'default': True,
                    'map_to': 'os',
                },
            ]
```

# Creating a workflow plugin

Workflow plugins can be created to override the native workflow behavior and extend functionality.<br>

## Create a directory under `agentpilot/plugins` to store your plugin

Inside the directory:
- Create a folder named `modules`
- Create a folder called `src` if you want to include any source code
- Create a file called `__init__.py` in all new folders so they're recognized by python
- Create a file called `workflow_plugin.py` in the `modules` folder

Your directory structure should look like this:

```bash
agentpilot
├── ...
├── plugins
│   ├── __init__.py
│   └── my_plugin
│       ├── __init__.py
│       └── modules
│           ├── __init__.py
│           └── workflow_plugin.py
├── ...
```

## Inside `workflow_plugin.py`:

### Import the WorkflowBehaviour base class

```python
from context.base import WorkflowBehaviour
```

### Create a class that inherits from WorkflowBehaviour

```python
from src.members.workflow import WorkflowBehaviour


class My_Plugin(WorkflowBehaviour):  # Unlike agent plugins, the app doesn't use class name anywhere.
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
```

### Add a `group_key` attribute

```python
from src.members.workflow import WorkflowBehaviour


class My_Plugin(WorkflowBehaviour):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.group_key = 'my_plugin'  # This must match the name of the plugin directory
```
When all agents in a workflow share a common `group_key` attribute, 
the workflow behaviour is inherited from the corresponding context plugin that matches the `group_key`.

Example:

```python
from src.members.agent import Agent
from src.plugins.crewai.src.agent import Agent as CAIAgent
from src.plugins.crewai.src.task import Task as CAITask

class CrewAI_Agent(Agent):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.group_key = 'crewai'  # Must match the directory name of the context plugin
        # If all agents in a group have the same key, the corresponding context plugin will be used
        self.agent_object = None
        self.agent_task = None
        ...
```

```python
from src.members.workflow import WorkflowBehaviour
from src.plugins.crewai.src.crew import Crew


class CrewAI_Context(WorkflowBehaviour):
    def __init__(self, workflow):
        super().__init__(workflow=workflow)
        self.group_key = 'crewai'
        self.crew = None
```
