from plugins.workflows.members import Member
from utils.helpers import set_module_type


@set_module_type(module_type='Members')
class Node(Member):
    workflow_insert_mode = 'single'
    allow_condition = False
    OUTPUT = None

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.input_passthrough = True
        self.receivable_function = None

    def load(self):
        pass