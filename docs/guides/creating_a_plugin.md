# Creating an agent plugin

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

### Overridable methods:
- <b>stream()</b> - This generator function is used for streaming a response. It must yield a tuple of (key, chunk) where key is either `assistant` or `code` and chunk is the response data. If streaming isn't support just yield the entire response as a single chunk.
- <b>load_agent()</b> - This method is called when the plugin is loaded. If overriding this method, make sure to call `super().load_agent()` to load the base agent.
- <b>system_message()</b> - This function is used to retrieve the system message for the agent. It can be overridden to return a custom system message. You can access the default system message by using `super().system_message()`.

### Base attributes:
- <b>self.context</b> - Using this you can access all methods and attributes of the current `Context`.

### Creating custom parameters:
You can create additional settings for an agent by defining a `custom_parameters` attribute. <br>
This is a dictionary of config names and types, and the values will be available in `self.config` with a prefixed key: `'external.{param_name}'`.<br>
The GUI will automatically create a setting for each parameter in the `General` tab of `AgentSettings`.

Available types:
- `str` - Text field
- `bool` - Checkbox
- `int` - Numeric
- `float` - Numeric

### Creating instance parameters
Sometimes (but not always) you may want to create instance parameters that are unique to each agent instance.<br>
These differ from a context member config (when a new chat is created, the member config is copied too, but the instance config is not).<br>
An example of this used practically is in the OpenAI Assistant agent plugin, where each agent instance has an `assistant_id` and a `thread_id`.

To define instance parameters, create an `instance_params` attribute in your agent plugin class. <br>
This is a dictionary of parameter names and values, and the values will be available in `self.config` with a prefixed key: `'instance.{param_name}'`.


### Example:
```python
from agentpilot.agent.base import Agent

        self.external_params = {
            'instructions': str,
            'code_interpreter': bool,
        }
```