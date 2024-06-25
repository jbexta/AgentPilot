from abc import abstractmethod


class Member:
    def __init__(self, **kwargs):  #  main, workflow, m_id, inputs):
        self.main = kwargs.get('main')
        self.workflow = kwargs.get('workflow', None)
        self.config = {}

        self.member_id = kwargs.get('member_id', 1)
        # self._member_id = kwargs.get('member_id', 1)
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

    # @property
    # def member_id(self):
    #     prefix = self.get_id_path_prefix()
    #     return f"{prefix}.{self._member_id}" if prefix != '' else str(self._member_id)
    #     # return f"{self.get_id_path_prefix()}.{self._member_id}"  # getattr(self, '_member_id', self._get_from_parent('_member_id'))
    #
    # @member_id.setter
    # def member_id(self, value):
    #     self._member_id = value

    def get_id_path_prefix(self):
        # bubble up to the top level workflow
        id_list = []
        parent = getattr(self, '_parent_workflow', None)
        while parent:
            id_list.append(parent.member_id)
            parent = getattr(parent, '_parent_workflow', None)
        # return '.'.join(reversed(id_list))  < map to str
        return '.'.join(map(str, reversed(id_list)))
