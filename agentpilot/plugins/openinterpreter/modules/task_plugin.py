from plugins.plugin import TaskPlugin
from plugins.openinterpreter.src.core.core import Interpreter


class OpenInterpreter_TaskPlugin(TaskPlugin):  # todo - inherit from base action for programatic control?
    def __init__(self, parent_task):
        self.agent_object = Interpreter()
        self.parent_task = parent_task

    def run(self):
        return_objs = {
            'msg': '',
            'language': '',
            'code': '',
            'output': '',
        }
        for chunk in self.agent_object.streaming_chat(message=self.parent_task.objective, display=False):
            if 'message' in chunk:
                return_objs['msg'] += chunk['message']
            elif 'language' in chunk:
                return_objs['language'] = chunk['language']
            elif 'code' in chunk:
                return_objs['code'] = chunk['code']
            elif 'output' in chunk:
                return_objs['output'] += chunk['output']
            elif 'CONFIRM' in chunk:
                break
            elif 'end_of_execution' in chunk:
                break

        return True, '[SAY]'
