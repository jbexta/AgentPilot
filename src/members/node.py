
from src.members.base import Member


class Node(Member):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.receivable_function = None

    def load(self):
        pass
