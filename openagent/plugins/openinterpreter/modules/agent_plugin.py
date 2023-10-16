from plugins.plugin import AgentPlugin
from plugins.openinterpreter.src.core.core import Interpreter


class OpenInterpreter_AgentPlugin(AgentPlugin):
    def __init__(self, base_agent):
        super().__init__()
        self.base_agent = base_agent
        self.agent_object = Interpreter()
        self.stream_object_base = self.agent_object.get_chat_stream
        self.stream_object = None  # self.stream_object_base(base_agent)  # None
        self.system_msg = self.agent_object.system_message
        # self.enforced_config_when_forced

    def hook_stream(self):
        # print('CALLED hook_stream : messages = ' + str(messages))
        self.stream_object = self.stream_object_base(self.base_agent)

        try:
            yield from self.stream_object
        except StopIteration as e:
            return e.value
        # for y in self.run_stream():
        #     yield y

    # def run_stream(self):
    #     yield from self.stream_object
