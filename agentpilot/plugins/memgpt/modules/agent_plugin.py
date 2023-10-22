import asyncio
import json
import os

import plugins.memgpt.src.interface as interface
from plugins.memgpt.src import utils
from plugins.memgpt.src.persistence_manager import InMemoryStateManager
from plugins.memgpt.src.humans import humans
from plugins.memgpt.src.personas import personas
from plugins.memgpt.src import presets  # , persistence_manager
from plugins.plugin import AgentPlugin
# from plugins.memgpt.src import agent

# class OpenInterpreter_AgentPlugin(AgentPlugin):
#     def __init__(self, base_agent):
#         super().__init__()
#         self.base_agent = base_agent
#         self.agent_object = Interpreter()
#         self.stream_object_base = self.agent_object.get_chat_stream
#         self.stream_object = None  # self.stream_object_base(base_agent)  # None
#         self.system_msg = self.agent_object.system_message
#         # self.enforced_config_when_forced
#
#     def hook_stream(self):
#         # print('CALLED hook_stream : messages = ' + str(messages))
#         self.stream_object = self.stream_object_base(self.base_agent)
#
#         try:
#             yield from self.stream_object
#         except StopIteration as e:
#             return e.value

class MemGPT_AgentPlugin(AgentPlugin):
    def __init__(self, base_agent):
        super().__init__()
        self.base_agent = base_agent
        persona = personas.DEFAULT
        human = humans.DEFAULT

        persistence_manager = InMemoryStateManager()
        self.agent_object = presets.use_preset(presets.DEFAULT, 'gpt-4', personas.get_persona_text(persona), humans.get_human_text(human), interface, persistence_manager)
        # self.enforced_config_when_forced

    def hook_stream(self):
        # print('CALLED hook_stream : messages = ' + str(messages))
        last_user_message = self.base_agent.context.message_history.last(incl_roles=['user'])
        new_messages, heartbeat_request, function_failed, token_warning = asyncio.run(self._async_hook_stream(last_user_message))
        if len(new_messages) < 2:
            raise NotImplementedError()
        oai_obj = new_messages[1]
        if 'function_call' in oai_obj:
            message_json_str = oai_obj['function_call']['arguments']
            message_json = json.loads(message_json_str)
            if 'message' in message_json:
                yield 'assistant', message_json['message']
            else:
                raise NotImplementedError()

        filename = utils.get_local_time().replace(' ', '_').replace(':', '_')
        filename = f"{filename}.json"
        filename = os.path.join('saved_state', filename)
        try:
            if not os.path.exists("saved_state"):
                os.makedirs("saved_state")
            self.agent_object.save_to_json_file(filename)
            print(f"Saved checkpoint to: {filename}")
        except Exception as e:
            print(f"Saving state to {filename} failed with: {e}")

        # save the persistence manager too
        filename = filename.replace('.json', '.persistence.pickle')
        try:
            self.agent_object.persistence_manager.save(filename)
            print(f"Saved persistence manager to: {filename}")
        except Exception as e:
            print(f"Saving persistence manager to {filename} failed with: {e}")

            yield 'PAUSE', ''

        dd = 1
        # yield 'assistant', 'Hello, I am MemGPT. How can I help you?'

    async def _async_hook_stream(self, user_message):
        return await self.agent_object.step(user_message, first_message=False, skip_verify=False)