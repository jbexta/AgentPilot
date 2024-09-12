from abc import abstractmethod


class Member:
    def __init__(self, **kwargs):
        self.main = kwargs.get('main')
        self.workflow = kwargs.get('workflow', None)
        self.config = kwargs.get('config', {})

        self.member_id = kwargs.get('member_id', 1)
        self.loc_x = kwargs.get('loc_x', 0)
        self.loc_y = kwargs.get('loc_y', 0)
        self.inputs = kwargs.get('inputs', [])

        self.last_output = None
        self.turn_output = None
        self.response_task = None

    def load(self):
        pass

    @abstractmethod
    async def run_member(self):
        """The entry response method for the member."""
        pass

    def get_id_path_prefix(self):
        # bubble up to the top level workflow
        id_list = []
        parent = getattr(self, '_parent_workflow', None)
        while parent:
            id_list.append(parent.member_id)
            parent = getattr(parent, '_parent_workflow', None)

        return '.'.join(map(str, reversed(id_list)))
