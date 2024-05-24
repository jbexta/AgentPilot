from abc import abstractmethod


class Member:
    def __init__(self, **kwargs):  #  main, workflow, m_id, inputs):
        self.main = kwargs.get('main')
        self.workflow = kwargs.get('workflow', None)
        self.config = {}

        self.member_id = kwargs.get('member_id', 1)
        self.loc_x = kwargs.get('loc_x', 0)
        self.loc_y = kwargs.get('loc_y', 0)
        self.inputs = kwargs.get('inputs', [])

        self.last_output = None
        self.turn_output = None
        self.response_task = None

    @abstractmethod
    async def run_member(self):
        """The entry response method for the member."""
        pass
