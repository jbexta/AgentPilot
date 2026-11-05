
from core.managers.modules import ModulesController


class MembersController(ModulesController):
    def __init__(self, system):
        super().__init__(
            system, 
            module_type='members', 
            load_to_path='plugins.workflows.members',
            class_based=True,
            inherit_from='Member',
            description="Workflow member modules",
            long_description="Member modules define the different types of members available in a Workflow"
        )
