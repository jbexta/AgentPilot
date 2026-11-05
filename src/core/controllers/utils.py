from core.managers.modules import ModulesController


class UtilsController(ModulesController):
    def __init__(self, system):
        super().__init__(
            system,
            module_type='utils',
            load_to_path='core.utils',
            class_based=False,
            inherit_from=None,
            description="Shared helper functions",
            long_description="Util modules are plain collections of functions and "
                             "constants - unlike every other module type they contain no class"
        )

    def get_plugin_module_dirs(self):
        # Suppressed: the base implementation matches on the last segment of
        # ``load_to_path``, which would slurp the pre-existing
        # ``src/plugins/*/utils/`` helper folders. Remove to let plugins ship
        # registered util modules.
        return iter(())
