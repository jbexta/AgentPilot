from core.managers.modules import ModulesController


class AudioEffectsController(ModulesController):
    def __init__(self, system):
        super().__init__(
            system,
            module_type='audio_effects',
            load_to_path='plugins.studio.effects.audio',
            class_based=True,
            description="Audio effects modules",
            long_description="Audio effects modules define sound transformations and filters for audio"
        )
