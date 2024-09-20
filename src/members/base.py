from abc import abstractmethod


class Member:
    def __init__(self, **kwargs):
        self.main = kwargs.get('main')
        self.workflow = kwargs.get('workflow', None)
        self.config = kwargs.get('config', {})

        self.member_id = kwargs.get('member_id', '1')
        self.loc_x = kwargs.get('loc_x', 0)
        self.loc_y = kwargs.get('loc_y', 0)
        self.inputs = kwargs.get('inputs', [])

        self.last_output = None
        self.turn_output = None
        self.response_task = None

    def load(self):
        pass

    def full_member_id(self):
        # bubble up to the top level workflow collecting member ids, return as a string joined with "." and reversed
        # where self._parent_workflow is None, that's the top level workflow
        id_list = [self.member_id]
        parent = self.workflow  #_parent_workflow
        while parent:
            if getattr(parent, '_parent_workflow', None) is None:
                break
            id_list.append(parent.member_id)
            parent = parent.workflow
        return '.'.join(map(str, reversed(id_list)))

    @abstractmethod
    async def run_member(self):
        """The entry response method for the member."""
        pass
