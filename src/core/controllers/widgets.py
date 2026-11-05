from core.managers.modules import ModulesController


class WidgetsController(ModulesController):
    def __init__(self, system):
        super().__init__(
            system, 
            module_type='widgets', 
            load_to_path='gui.widgets',
            class_based=True,
            inherit_from='QWidget',
            description="Reusable UI widget components",
            long_description="Widgets are QWidget modules that can be used within pages or linked as a Member settings widget."
        )
    
    def preview_widget(self, cls):
        return cls