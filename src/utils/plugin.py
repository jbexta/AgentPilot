# import importlib
# import inspect
#
# from PySide6.QtGui import QPalette, Qt
# from PySide6.QtWidgets import QStyle, QStyleOptionComboBox, QStylePainter

# from src.agent.base import Agent
# from src.gui.widgets.base import BaseComboBox, AlignDelegate

# AGENT PLUGINS
from src.plugins.openinterpreter.modules.agent_plugin import Open_Interpreter
from src.plugins.openaiassistant.modules.agent_plugin import OpenAI_Assistant
from src.plugins.crewai.modules.agent_plugin import CrewAI_Agent
from src.plugins.crewai.modules.context_plugin import CrewAI_Workflow
# from agentpilot.plugins.autogen.modules.agent_plugin import


all_plugins = {
    'Agent': [
        Open_Interpreter,
        CrewAI_Agent,
        OpenAI_Assistant,
    ],
    'Workflow': {
        'crewai': CrewAI_Workflow,
    },
}


def get_plugin_agent_class(plugin_name, kwargs=None):
    if not plugin_name:
        return None  # Agent(**kwargs)
    if kwargs is None:
        kwargs = {}

    clss = next((AC(**kwargs) for AC in all_plugins['Agent'] if AC.__name__ == plugin_name), None)
    return clss


# def get_plugin_workflow_class(plugin_name, kwargs=None):
#     if not plugin_name:
#         return None  # Agent(**kwargs)
#     if kwargs is None:
#         kwargs = {}
#
#     clss = next((AC(**kwargs) for AC in agent_plugins['Workflow'] if AC.__name__ == plugin_name), None)
#     return clss
