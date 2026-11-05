
from core.managers.modules import ModulesController


class ProvidersController(ModulesController):
    def __init__(self, system):
        super().__init__(
            system, 
            module_type='providers', 
            load_to_path='plugins.workflows.providers',
            class_based=True,
            inherit_from='Provider',
            description="AI model provider modules",
            long_description="Provider modules serve AI models from a dedicated service"
        )
