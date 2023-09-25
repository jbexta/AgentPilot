# # from agent import base
# from agent.base import Agent
# from operations.openinterpreter.core.core import Interpreter
#
#
# class AgentPlugin(Agent):  # todo - refactor
#     def __init__(self):
#         super().__init__()
#         # self.agent_object = None
#         # self.stream_object = None
#         # self.system_msg = ''
#
#
# class OpenInterpreter_AgentPlugin(AgentPlugin):
#     def __init__(self):
#         super().__init__()
#         self.agent_object = Interpreter()
#         self.stream_object = self.agent_object.chat
#         self.system_msg = self.agent_object.system_message
#         # self.enforced_config_when_forced
#
#     def hook_stream(self):
#         # map stream output {'type': chunk} to yield just chunk
#         for resp in self.stream_object():
#             yield resp
#
#
# class TaskPlugin:
#     def __init__(self):
#         super().__init__()
#
#
# class OpenInterpreter_TaskPlugin:  # todo - inherit from base action for programatic control?
#     def __init__(self, parent_task):
#         self.agent_object = Interpreter()
#         self.parent_task = parent_task
#
#     def run(self):
#         return_objs = {
#             'msg': '',
#             'language': '',
#             'code': '',
#             'output': '',
#         }
#         for chunk in self.agent_object.streaming_chat(message=self.parent_task.objective, display=False):
#             if 'message' in chunk:
#                 return_objs['msg'] += chunk['message']
#             elif 'language' in chunk:
#                 return_objs['language'] = chunk['language']
#             elif 'code' in chunk:
#                 return_objs['code'] = chunk['code']
#             elif 'output' in chunk:
#                 return_objs['output'] += chunk['output']
#             elif 'confirm_execution' in chunk:
#                 break
#             elif 'end_of_execution' in chunk:
#                 break
#
#         return True, '[SAY]'
