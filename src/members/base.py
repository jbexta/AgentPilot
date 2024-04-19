from abc import abstractmethod


class Member:
    def __init__(self, main, workflow, m_id, inputs):
        self.main = main
        self.workflow = workflow
        self.m_id = m_id
        # self.agent = agent
        self.inputs = inputs if inputs else []
        self.response_task = None
        self.last_output = ''

    @abstractmethod
    def run_member(self):
        """The entry response method for the member."""
        pass
