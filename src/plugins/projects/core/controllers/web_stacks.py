from core.managers.modules import ModulesController


class WebStacksController(ModulesController):
    def __init__(self, system):
        super().__init__(
            system,
            module_type='web_stacks',
            load_to_path='plugins.projects.core.web_stacks',
            description='Website stack modules',
            long_description='Runtimes that serve a Website project: how to '
                             'recognise one, what to run for it, and where '
                             'the preview points',
        )
