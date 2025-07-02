
from members import Member
from utils.helpers import set_module_type


@set_module_type(module_type='Members')
class Node(Member):
    OUTPUT = None

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.input_passthrough = True
        self.receivable_function = None

    def load(self):
        pass
