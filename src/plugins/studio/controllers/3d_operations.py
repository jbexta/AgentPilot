from core.managers.modules import ModulesController
##

class ThreeDOperationsController(ModulesController):
    def __init__(self, system):
        super().__init__(
            system,
            module_type='3d_operations',
            load_to_path='plugins.studio.operations.3d',
            class_based=True,
            description="3D operation modules",
            long_description="AI-powered 3D operations (generate, remix, etc.)"
        )
