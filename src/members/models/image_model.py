
from src.members import Model
from src.utils.helpers import set_module_type


@set_module_type(module_type='Members', plugin='MODEL', settings='ImageModelSettings')
class ImageModel(Model):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    async def receive(self):
        """The entry response method for the member."""
        yield self.default_role(), 'TODO'
        # content = self.get_content()
        # yield self.default_role(), content
        # self.workflow.save_message(self.default_role(), content, self.full_member_id())  # , logging_obj)
