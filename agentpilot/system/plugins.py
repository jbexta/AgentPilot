


class PluginManager:
    def __init__(self):
        pass

    def load(self):
        pass

# def get_all_plugin_agents(self):
#     # iterate all agent folders in "agentpilot.plugins" folder
#     for plugin_name in importlib.import_module("agentpilot.plugins").__dict__.keys():
#         if not plugin_name.startswith("__"):
#             # iterate all classes in the agent folder
#             for AC in importlib.import_module(f"agentpilot.plugins.{plugin_name}.modules.agent_plugin").__dict__.values():
#                 # check if the class is a subclass of Agent
#                 if inspect.isclass(AC) and issubclass(AC, Agent) and not AC.__name__ == 'Agent':
#                     # return the class
#                     yield AC


# and return all classes that are subclass of Agent
# and not the Agent class itself



# all_agent_plugins = [AC for AC in
#                      importlib.import_module(f"agentpilot.plugins").__dict__.values()
#                      if inspect.isclass(AC) and issubclass(AC, Agent) and not AC.__name__ == 'Agent']

