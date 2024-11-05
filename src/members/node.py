
from src.members.base import Member


class Node(Member):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.receivable_function = None
        # self.receivable = False

    def load(self):
        pass

    # async def run_member(self):
    #     """The entry response method for the member."""
    #     yield 'SYS', 'SKIP'
