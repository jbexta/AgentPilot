import time
import openai
from PySide6.QtWidgets import QMessageBox
from openai import OpenAI
from openai.types.beta import CodeInterpreterTool
from openai.types.beta.assistant_stream_event import ThreadMessageDelta

from src.gui.config import ConfigFields
from src.members.agent import Agent, AgentSettings
from src.utils.helpers import display_message_box


class OpenAI_Assistant(Agent):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.client = None
        self.assistant = None

    # def load_agent(self):
    #     super().load_agent()
    #     # ADD CHECK FOR CHANGED CONFIG, IF INVALID, RECREATE ASSISTANT

    def find_assistant(self):  # todo rethink, maybe reintroduce instance config
        name = self.config.get('info.name', 'Assistant')
        instructions = self.system_message()
        model = self.config.get('chat.model', 'gpt-3.5-turbo')
        code_interpreter = self.config.get('plugin.code_interpreter', True)
        pass

        try:
            assistants = self.client.beta.assistants.list(limit=100)

            for assistant in assistants.data:
                tools = assistant.tools
                has_ci = isinstance(tools, list) and len(tools) == 1 and isinstance(tools[0], CodeInterpreterTool)
                ci_match = has_ci == code_interpreter
                if assistant.name == name and \
                        assistant.instructions == instructions and \
                        assistant.model == model and \
                        ci_match:
                        # assistant.tools == (["type": "code_interpreter"] if code_interpreter else []):
                    pass
                    return assistant.id

            return None

        except Exception as e:
            raise e

    def initialize_assistant(self):
        if self.assistant is None:
            model_name = self.config.get('chat.model', 'gpt-3.5-turbo')
            model_params = self.workflow.main.system.providers.get_model_parameters(model_name)
            api_key = model_params.get('api_key', None)
            api_base = model_params.get('api_base', None)
            self.client = OpenAI(api_key=api_key, base_url=api_base)

            ass_id = self.find_assistant()
            if ass_id:
                self.assistant = self.client.beta.assistants.retrieve(ass_id)
            else:
                self.assistant = self.create_assistant()

    def create_assistant(self):
        name = self.config.get('info.name', 'Assistant')
        model_name = self.config.get('chat.model', 'gpt-3.5-turbo')
        system_msg = self.system_message()

        code_interpreter = self.config.get('plugin.Code Interpreter', True)
        tools = [] if not code_interpreter else [{"type": "code_interpreter"}]
        return self.client.beta.assistants.create(
            name=name,
            instructions=system_msg,
            model=model_name,
            tools=tools,
        )

        # # self.update_instance_config('assistant_id', assistant.id)

    # MERGE INTO config
    # - IGNORE INSTANCE PARAMS WHEN update_agent_config IS CALLED
    # - IGNORE AGENT PARAMS WHEN update_instance_config IS CALLED
    # WHEN YOU MODIFY THE PLUGIN CONFIG, IT SHOULD RELOAD THE AGENT

    async def stream(self, *args, **kwargs):
        if self.assistant is None:
            self.initialize_assistant()

        messages = kwargs.get('messages', [])

        run = self.client.beta.threads.create_and_run(
            assistant_id=self.assistant.id,
            stream=True,
            thread={
                "messages": messages
            }
        )

        for event in run:
            if not isinstance(event, ThreadMessageDelta):
                continue
            chunk = event.data.delta.content[0].text.value
            yield 'assistant', chunk


class OAIAssistantSettings(AgentSettings):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # self.pages.pop('Files')
        info_widget = self.pages['Info']
        info_widget.widgets.append(self.Plugin_Fields(parent=info_widget))

    class Plugin_Fields(ConfigFields):
        def __init__(self, parent):
            super().__init__(parent=parent)
            self.parent = parent
            self.conf_namespace = 'plugin'
            self.schema = [
                {
                    'text': 'Code Interpreter',
                    'type': bool,
                    'default': True,
                    'width': 175,
                },
            ]
