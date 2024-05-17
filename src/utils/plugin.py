# import importlib
# import inspect
#
# from PySide6.QtGui import QPalette, Qt
# from PySide6.QtWidgets import QStyle, QStyleOptionComboBox, QStylePainter
from src.members.agent import AgentSettings
# from src.agent.base import Agent
# from src.gui.widgets import BaseComboBox, AlignDelegate

# AGENT PLUGINS
# from src.plugins.openinterpreter.modules.agent_plugin import Open_Interpreter
from src.plugins.openaiassistant.modules.agent_plugin import OpenAI_Assistant, OAIAssistantSettings
from src.plugins.crewai.modules.agent_plugin import CrewAI_Agent
from src.plugins.crewai.modules.context_plugin import CrewAI_Workflow
# from src.plugins.awspolly.modules.tts_plugin import AWS_Polly_TTS
# from agentpilot.plugins.autogen.modules.agent_plugin import


all_plugins = {
    'Agent': [
        # Open_Interpreter,
        CrewAI_Agent,
        OpenAI_Assistant,
    ],
    'AgentSettings': {
        'OpenAI_Assistant': OAIAssistantSettings,
    },
    'Workflow': {
        'crewai': CrewAI_Workflow,
    },
    # 'TTS_API': [
    #     AWS_Polly_TTS  # todo
    # ]
}


def get_plugin_agent_class(plugin_name, kwargs=None):
    if not plugin_name:
        return None  # Agent(**kwargs)
    if kwargs is None:
        kwargs = {}

    clss = next((AC(**kwargs) for AC in all_plugins['Agent'] if AC.__name__ == plugin_name), None)
    return clss


def get_plugin_agent_settings(plugin_name):
    clss = all_plugins['AgentSettings'].get(plugin_name, AgentSettings)
    class AgentMemberSettings(clss):
        def __init__(self, parent):
            super().__init__(parent)
            self._plugin_name = plugin_name
            self.member_id = None

        def update_config(self):
            self.save_config()

        def save_config(self):
            conf = self.get_config()
            self.parent.members_in_view[self.member_id].member_config = conf
            self.parent.save_config()
    # AgentMemberSettings._plugin_name = plugin_name
    return AgentMemberSettings

    # return clss or AgentSettings

# def get_plugin_workflow_class(plugin_name, kwargs=None):
#     if not plugin_name:
#         return None  # Agent(**kwargs)
#     if kwargs is None:
#         kwargs = {}
#
#     clss = next((AC(**kwargs) for AC in agent_plugins['Workflow'] if AC.__name__ == plugin_name), None)
#     return clss
