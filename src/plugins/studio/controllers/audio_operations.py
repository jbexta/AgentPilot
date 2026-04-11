from core.managers.modules import ModulesController


class AudioOperationsController(ModulesController):
    def __init__(self, system):
        super().__init__(
            system,
            module_type='audio_operations',
            load_to_path='plugins.studio.operations.audio',
            class_based=True,
            description="Audio operation modules",
            long_description="AI-powered audio operations (remix, extend, transcribe, etc.)"
        )
