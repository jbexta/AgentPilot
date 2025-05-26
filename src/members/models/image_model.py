
from src.members import Model
from src.utils.helpers import set_module_type


@set_module_type(module_type='Members', plugin='MODEL', settings='ImageModelSettings')
class ImageModel(Model):
    default_role = 'image'

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    async def receive(self):
        """The entry response method for the member."""
        yield self.default_role, 'TODO'
