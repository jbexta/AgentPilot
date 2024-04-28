from abc import abstractmethod
from src.members.base import Member


class User(Member):
    def __init__(self, main=None, workflow=None, member_id=None, config=None, inputs=None):
        super().__init__(main=main, workflow=workflow, m_id=member_id, inputs=inputs)
        self.workflow = workflow
        self.config = config or {}

    @abstractmethod
    def run_member(self):
        """The entry response method for the member."""
        pass
