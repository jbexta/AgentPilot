from core.managers.modules import ModulesController


class ManagersController(ModulesController):
    def __init__(self, system):
        super().__init__(
            system, 
            module_type='managers', 
            load_to_path='core.managers',
            class_based=True,
            inherit_from='BaseManager',
            description="System-level management modules",
            long_description="Manager modules are initialized on startup, these often load and save data to a specific database table."
        )