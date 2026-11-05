from core.managers.modules import ModulesController


class ImageToolsController(ModulesController):
    def __init__(self, system):
        super().__init__(
            system,
            module_type='image_tools',
            load_to_path='plugins.studio.tools.image',
            class_based=True,
            description="Image studio tools",
            long_description="Image tool modules define the canvas tools (brush, eraser, etc.) used by the image studio."
        )
