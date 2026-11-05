from core.managers.modules import ModulesController


class GuiUtilsController(ModulesController):
    def __init__(self, system):
        super().__init__(
            system,
            module_type='gui_utils',
            load_to_path='gui.gui_utils',
            class_based=True,
            inherit_from=None,
            description="Shared GUI building blocks",
            long_description="Gui util modules are small reusable Qt classes - "
                             "buttons, menus, dialogs, delegates and layouts - "
                             "used by widgets, fields and pages"
        )
