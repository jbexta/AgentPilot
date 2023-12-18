import importlib
import inspect
from agentpilot.agent.base import Agent


def get_plugin_agent_class(plugin_name, kwargs):
    if not plugin_name:
        return Agent(**kwargs)

    return next((AC(**kwargs)
                 for AC in importlib.import_module(
        f"agentpilot.plugins.{plugin_name}.modules.agent_plugin").__dict__.values()
                 if inspect.isclass(AC) and issubclass(AC, Agent) and not AC.__name__ == 'Agent'),
                None)