from abc import abstractmethod


class Member:
    def __init__(self, **kwargs):  #  main, workflow, m_id, inputs):
        self.main = kwargs.get('main')
        self.workflow = kwargs.get('workflow', None)
        self.m_id = kwargs.get('m_id', 0)
        self.config = {}
        # self.agent = agent
        self.inputs = kwargs.get('inputs', [])
        self.response_task = None
        self.last_output = ''
        self.loc_x = kwargs.get('loc_x', 0)
        self.loc_y = kwargs.get('loc_y', 0)

    @abstractmethod
    async def run_member(self):
        """The entry response method for the member."""
        pass
