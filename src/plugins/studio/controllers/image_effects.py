from core.managers.modules import ModulesController


class ImageEffectsController(ModulesController):
    def __init__(self, system):
        super().__init__(
            system,
            module_type='image_effects',
            load_to_path='plugins.studio.effects.image',
            class_based=True,
            description="Image effects controllers",
            long_description="Image effects modules define visual transformations and filters for images and videos"
        )
