# Table of Contents
- [Creating an agent plugin](#creating-an-agent-plugin)
  - [Create a directory under `agentpilot/plugins` to store your plugin](#create-a-directory-under-agentpilotplugins-to-store-your-plugin)
  - [Inside `agent_plugin.py`](#inside-agent_pluginpy)
    - [Import the Agent base class](#import-the-agent-base-class)
    - [Create a class that inherits from Agent](#create-a-class-that-inherits-from-agent)
    - [Overridable methods](#overridable-methods)
    - [Overridable attributes](#overridable-attributes)
    - [Creating extra parameters](#creating-extra-parameters)
    - [Creating instance parameters](#creating-instance-parameters)
    - [Example](#example)
- [Creating a context plugin](#creating-a-context-plugin)
  - [Create a directory under `agentpilot/plugins` to store your plugin](#create-a-directory-under-agentpilotplugins-to-store-your-plugin-1)
  - [Inside `context_plugin.py`](#inside-context_pluginpy)
    - [Import the Context base class](#import-the-context-base-class)
    - [Create a class that inherits from Context](#create-a-class-that-inherits-from-context)
    - [Overridable methods](#overridable-methods-1)
    - [Overridable attributes](#overridable-attributes-1)
    - [Creating extra parameters](#creating-extra-parameters-1)
    - [Creating instance parameters](#creating-instance-parameters-1)
    - [Example:](#example-1)

# Creating an agent plugin

Agent plugins can be created to override the native agent behavior and extend functionality.<br>

## Create a directory under `agentpilot/plugins` to store your plugin

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
from agentpilot.agent.base import Agent
```

### Create a class that inherits from Agent
```python
class My_Plugin(Agent):  # The app will use this class name in the plugin dropdown menu.
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
```


Now from your agent plugin class, you can override methods and access the base attributes by using `self` or `super()`.

### Overridable methods
- <b>stream()</b> - This generator function is used for streaming a response. It must yield a tuple of (key, chunk) where key is either `assistant` or `code` and chunk is the response data. If streaming isn't support just yield the entire response as a single chunk.
- <b>load_agent()</b> - This method is called when the plugin is loaded. If overriding this method, make sure to call `super().load_agent()` to load the base agent.
- <b>system_message()</b> - This function is used to retrieve the system message for the agent. It can be overridden to return a custom system message. You can access the default system message by using `super().system_message()`.

### Overridable attributes
- <b>self.context</b> - Using this you can access all methods and attributes of the current `Context`.

### Creating extra parameters
You can create additional settings for an agent by defining a `extra_params` attribute. <br>
This is a list of dictionaries representing a list of parameters. The values will be available in the GUI and `self.config` with a prefixed key: `'extra.{param_name}'`.<br>
The GUI will automatically create a setting for each parameter in the `General` tab of `AgentSettings`.<br>
This is useful for creating settings that modify external configs.

Available types:
- `str` - Text field
- `bool` - Checkbox
- `int` - Numeric
- `float` - Numeric
- `tuple` - Combobox (This should be an instance of a tuple, not the type)

### Creating instance parameters
Sometimes (but not always) you may want to create instance parameters that are unique to each agent instance.<br>
These differ from a context member config (when a new chat is created, the member config is copied too, but the instance config is not).<br>
An example of this used practically is in the OpenAI Assistant agent plugin, where each agent instance has a unique `thread_id`.

To define instance parameters, create an `instance_params` attribute in your agent plugin class. <br>
This is a dictionary of parameter names and values, and the values will be available in `self.config` with a prefixed key: `'instance.{param_name}'`.


### Example
```python
from agentpilot.agent.base import Agent
from agentpilot.plugins.openinterpreter.src.core.core import OpenInterpreter

class Open_Interpreter(Agent):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        self.agent_object = OpenInterpreter()
        self.extra_params = [
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
            },
            {
                'text': 'Anonymous telemetry',
                'type': bool,
                'default': True,
                'map_to': 'anonymous_telemetry',
            },
            {
                'text': 'Force task completion',
                'type': bool,
                'default': False,
                'map_to': 'force_task_completion',
            },
            {
                'text': 'OS',
                'type': bool,
                'default': True,
                'map_to': 'os',
            },
        ]
```