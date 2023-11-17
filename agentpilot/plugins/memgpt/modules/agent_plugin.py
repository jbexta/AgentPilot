import asyncio
import json
import os

# import agentpilot.plugins.memgpt.src as memgpt
from agentpilot.plugins.memgpt.src.agent import Agent as memgpt_Agent
import agentpilot.plugins.memgpt.src.interface as interface
from agentpilot.plugins.memgpt.src import utils
from agentpilot.plugins.memgpt.src.persistence_manager import InMemoryStateManager
from agentpilot.plugins.memgpt.src.humans import humans
from agentpilot.plugins.memgpt.src.personas import personas  # , persistence_manager
from agentpilot.plugins.plugin import AgentPlugin
# from agentpilot.plugins.memgpt.src import agent

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
        self.agent_object = None
        # self.agent_object = memgpt_Agent(
        #     preset,
        #     agent_config,
        #     model,
        #     persona_description,
        #     user_description,
        #     interface,
        #     persistence_manager,
        # )
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
                field_name = message_json['name']
                old_content = f"{field_name}: {message_json['old_content']}"
                new_content = f"{field_name}: {message_json['new_content']}"
                common_prefix, unique_values = self.extract_common_prefix_and_changes(old_content, new_content)
                if common_prefix != '' and len(unique_values) == 2:
                    yield 'note', f"{message_json['name']}: {unique_values[0]} -> {unique_values[1]}"
                else:
                    fallback_line = f"{message_json['name']}: {message_json['old_content']} -> {message_json['new_content']}"
                    yield 'note', fallback_line

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

    def extract_common_prefix_and_changes(self, s1, s2):
        # Determine the length of the common prefix
        i = 0
        while i < len(s1) and i < len(s2) and s1[i] == s2[i]:
            i += 1

        # Adjust the index to avoid splitting words
        while i > 0 and s1[i - 1] != ' ':
            i -= 1

        # Split the strings at the end of the common prefix
        common_prefix = s1[:i].rstrip()  # rstrip to remove any trailing spaces
        unique_s1 = s1[i:]
        unique_s2 = s2[i:]

        # Return results based on the extracted values
        unique_values = [v for v in [unique_s1, unique_s2] if v]
        return common_prefix, unique_values