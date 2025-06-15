
from src.members import Member
from src.utils.helpers import set_module_type


@set_module_type(module_type='Members')
class Iterate(Member):
    default_avatar = ':/resources/icon-iterate.png'
    default_name = 'Iterator'
    OUTPUT = None


    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.receivable_function = None

    def load(self):
        pass
