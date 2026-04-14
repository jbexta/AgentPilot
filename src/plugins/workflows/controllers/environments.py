from core.managers.modules import ModulesController


class EnvironmentsController(ModulesController):
    def __init__(self, system):
        super().__init__(
            system, 
            module_type='environments', 
            load_to_path='plugins.workflows.environments',
            class_based=True,
            inherit_from=None,
            description="Code execution environment modules",
            long_description="Environment modules define a code execution environment"
        )