
from src.members.agent import AgentSettings
from src.members.block import TextBlockSettings, CodeBlockSettings, PromptBlockSettings, TextBlock, CodeBlock, \
    PromptBlock, ModuleBlock, ModuleBlockSettings, ModuleMethodSettings, ModuleVariableSettings
from src.plugins.docker.modules.sandbox_plugin import Docker, DockerSettings

# PROVIDER PLUGINS
from src.plugins.fakeyou.modules.provider_plugin import FakeYouProvider
from src.plugins.litellm.modules.provider_plugin import LitellmProvider

# AGENT PLUGINS
from src.plugins.openaiassistant.modules.agent_plugin import OpenAI_Assistant, OAIAssistantSettings
from src.plugins.openinterpreter.modules.agent_plugin import OpenInterpreterSettings, Open_Interpreter

# SANDBOX PLUGINS
# from src.plugins.e2b.modules.sandbox_plugin import E2BEnvironment
# from src.plugins.openllm.modules.provider_plugin import OpenllmProvider
from src.plugins.routellm.modules.provider_plugin import RoutellmProvider


class PluginManager:
    def __init__(self):
        pass

    def load(self):
        pass


ALL_PLUGINS = {
    'Agent': [
        Open_Interpreter,
        # CrewAI_Agent,
        OpenAI_Assistant,
        # Agent_Zero,
    ],
    'AgentSettings': {
        'Open_Interpreter': OpenInterpreterSettings,
        # 'CrewAI_Agent': CrewAIAgentSettings,
        'OpenAI_Assistant': OAIAssistantSettings,
        # 'Agent_Zero': AgentSettings,
    },
    'Block': {
        'Text': TextBlock,
        'Code': CodeBlock,
        'Prompt': PromptBlock,
        'Module': ModuleBlock,
    },
    'BlockSettings': {
        'Text': TextBlockSettings,
        'Code': CodeBlockSettings,
        'Prompt': PromptBlockSettings,
        'Module': ModuleBlockSettings,
    },
    'ModuleTargetSettings': {  # todo remove from plugins & integrate
        'Method': ModuleMethodSettings,
        'Variable': ModuleVariableSettings,
        'Tool': ModuleVariableSettings,
    },
    'Provider': {
        # 'openllm': OpenllmProvider,
        'litellm': LitellmProvider,
        'fakeyou': FakeYouProvider,
        'routellm': RoutellmProvider,
    },
    'Environment': [
        # E2BEnvironment,
        Docker,
    ],
    'EnvironmentSettings': {
        'Docker': DockerSettings
        # 'E2BSandbox': E2BSandboxSettings,
    },
    'Workflow': {
        # 'CrewAI': CrewAI_Workflow,
    },
    'WorkflowConfig': {
        # 'CrewAI': CrewAI_WorkflowConfig,
    },
    'VectorDBSettings': {}
    # # 'FineTune': [
    # #     OpenAI_Finetune,
    # #     Anyscale_Finetune,
    # # ],
    # # 'VectorDB': [
    # #     OpenAI_VectorDB,
    # #     # LanceDB_VectorDB,
    # # ],
}


def get_plugin_class(plugin_type, plugin_name, default_class=None):
    # if kwargs is None:
    #     kwargs = {}

    type_plugins = ALL_PLUGINS[plugin_type]
    if isinstance(type_plugins, list):
        clss = next((AC for AC in type_plugins if AC.__name__ == plugin_name), None)
    else:  # is dict
        clss = type_plugins.get(plugin_name, None)
    if clss is None:
        clss = default_class
    return clss


def get_plugin_agent_settings(plugin_name):
    clss = ALL_PLUGINS['AgentSettings'].get(plugin_name, AgentSettings)

    class AgentMemberSettings(clss):
        def __init__(self, parent):
            super().__init__(parent)
            self.parent = parent
            self._plugin_name = plugin_name
            self.member_id = None

        def update_config(self):
            self.save_config()

        def save_config(self):
            old_plugin = self.parent.members_in_view[self.member_id].member_config.get('info.use_plugin', '')

            conf = self.get_config()
            current_plugin = conf.get('info.use_plugin', '')
            self.parent.members_in_view[self.member_id].member_config = conf
            self.parent.update_config()

            is_different_plugin = old_plugin != current_plugin
            if is_different_plugin and hasattr(self.parent, 'on_selection_changed'):
                self.parent.on_selection_changed()  # reload the settings widget

    return AgentMemberSettings


def get_plugin_block_settings(plugin_name):
    if not plugin_name:
        plugin_name = 'Text'
    clss = ALL_PLUGINS['BlockSettings'].get(plugin_name, TextBlockSettings)  # , None)

    class BlockMemberSettings(clss):
        def __init__(self, parent):
            super().__init__(parent)
            self.parent = parent
            self._plugin_name = plugin_name
            self.member_id = None

        # def update_config(self):
        #     self.save_config()

        def save_config(self):
            old_plugin = self.parent.members_in_view[self.member_id].member_config.get('block_type', '')

            conf = self.get_config()
            current_plugin = conf.get('block_type', '')
            self.parent.members_in_view[self.member_id].member_config = conf
            self.parent.update_config()

            is_different_plugin = old_plugin != current_plugin
            if is_different_plugin and hasattr(self.parent, 'on_selection_changed'):
                self.parent.on_selection_changed()  # reload the settings widget

    return BlockMemberSettings


def get_plugin_workflow_config(plugin_name):
    clss = ALL_PLUGINS['WorkflowConfig'].get(plugin_name, None)
    return clss
