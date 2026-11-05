from core.managers.modules import ModulesController


class VideoOperationsController(ModulesController):
    def __init__(self, system):
        super().__init__(
            system,
            module_type='video_operations',
            load_to_path='plugins.studio.operations.video',
            class_based=True,
            description="Video operation modules",
            long_description="AI-powered video operations (remix, extend, transcribe, etc.)"
        )
