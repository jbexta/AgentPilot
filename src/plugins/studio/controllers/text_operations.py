from core.managers.modules import ModulesController


class TextOperationsController(ModulesController):
    def __init__(self, system):
        super().__init__(
            system,
            module_type='text_operations',
            load_to_path='plugins.studio.operations.text',
            class_based=True,
            description="Text operation modules",
            long_description="AI-powered text operations (summarize, translate, etc.)"
        )
