# import importlib
# import inspect
#
# from PySide6.QtGui import QPalette, Qt
# from PySide6.QtWidgets import QStyle, QStyleOptionComboBox, QStylePainter
from src.members.agent import AgentSettings
from src.plugins.e2b.modules.sandbox_plugin import E2BSandboxSettings, E2BSandbox
from src.plugins.fakeyou.modules.provider_plugin import FakeYouProvider
# from src.agent.base import Agent
# from src.gui.widgets import BaseComboBox, AlignDelegate

# AGENT PLUGINS
# from src.plugins.openinterpreter.modules.agent_plugin import Open_Interpreter
from src.plugins.openaiassistant.modules.agent_plugin import OpenAI_Assistant, OAIAssistantSettings
from src.plugins.crewai.modules.agent_plugin import CrewAI_Agent, CrewAIAgentSettings
from src.plugins.crewai.modules.context_plugin import CrewAI_Workflow
from src.plugins.openaiassistant.modules.vecdb_plugin import OpenAI_VectorDB
from src.plugins.openinterpreter.modules.agent_plugin import OpenInterpreterSettings, Open_Interpreter

# from src.plugins.awspolly.modules.tts_plugin import AWS_Polly_TTS
# from agentpilot.plugins.autogen.modules.agent_plugin import



class PluginManager:
    def __init__(self):
        pass

    def load(self):
        pass


all_plugins = {
    'Agent': [
        Open_Interpreter,
        CrewAI_Agent,
        OpenAI_Assistant,
    ],
    'AgentSettings': {
        'Open_Interpreter': OpenInterpreterSettings,
        'CrewAI_Agent': CrewAIAgentSettings,
        'OpenAI_Assistant': OAIAssistantSettings,
    },
    'WorkflowBehavior': {
        'crewai': CrewAI_Workflow,
    },
    # 'FineTune': [
    #     OpenAI_Finetune,
    #     Anyscale_Finetune,
    # ],
    'VectorDB': [
        OpenAI_VectorDB,
        # LanceDB_VectorDB,
    ],
    'Sandbox': [
        E2BSandbox,
    ],
    'SandboxSettings': {
        'E2BSandbox': E2BSandboxSettings,
    },
    'ProviderPlugin': [
        FakeYouProvider,
    ],
    'ProviderPluginSettings': {
        'FakeYouProvider': None,
        'ElevenLabsProvider': None,
        'LiteLLMProvider': None,  # ?
    }
    # 'Voices': [
    #     FakeYouVoices,
    # ]
}


def get_plugin_class(plugin_type, plugin_name, kwargs=None):
    if not plugin_name:
        return None  # Agent(**kwargs)
    if kwargs is None:
        kwargs = {}

    type_plugins = all_plugins[plugin_type]
    if isinstance(type_plugins, list):
        clss = next((AC(**kwargs) for AC in type_plugins if AC.__name__ == plugin_name), None)
        return clss
    elif isinstance(type_plugins, dict):
        clss = type_plugins.get(plugin_name, None)
        return clss


# def get_plugin_agent_class(plugin_name, kwargs=None):
#     if not plugin_name:
#         return None  # Agent(**kwargs)
#     if kwargs is None:
#         kwargs = {}
#
#     clss = next((AC(**kwargs) for AC in all_plugins['Agent'] if AC.__name__ == plugin_name), None)
#     return clss


def get_plugin_agent_settings(plugin_name):
    clss = all_plugins['AgentSettings'].get(plugin_name, AgentSettings)
    class AgentMemberSettings(clss):
        def __init__(self, parent):
            super().__init__(parent)
            self.parent = parent
            self._plugin_name = plugin_name
            self.member_id = None

        def update_config(self):
            self.save_config()

        def save_config(self):
            old_conf = self.parent.members_in_view[self.member_id].member_config
            conf = self.get_config()
            self.parent.members_in_view[self.member_id].member_config = conf
            self.parent.save_config()

            is_different_plugin = old_conf.get('info.use_plugin', '') != conf.get('info.use_plugin', '')
            if is_different_plugin and hasattr(self.parent, 'on_selection_changed'):
                self.parent.on_selection_changed()  # reload the settings widget
                # self.save_config()
                # conf = self.get_config()
                # self.parent.members_in_view[self.member_id].member_config = conf
                # self.parent.save_config()

                # self.parent.save_config()  # needed
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
