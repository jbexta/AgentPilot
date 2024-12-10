
from src.members.base import Member


class Node(Member):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.receivable_function = None

    def load(self):
        pass

    def allowed_inputs(self):
        return {'Flow': None}

    def allowed_outputs(self):
        return {'Output': str}
