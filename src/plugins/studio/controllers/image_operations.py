from core.managers.modules import ModulesController


class ImageOperationsController(ModulesController):
    def __init__(self, system):
        super().__init__(
            system,
            module_type='image_operations',
            load_to_path='plugins.studio.operations.image',
            class_based=True,
            description="Image operation modules",
            long_description="AI-powered image operations (remix, outpaint, etc.)"
        )
