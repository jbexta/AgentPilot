
from core.managers.modules import ModulesController


class ControllersController(ModulesController):
    def __init__(self, system):
        super().__init__(
            system, 
            module_type='project_types', 
            load_to_path='plugins.projects.gui.project_types',
            description='Project type modules',
            long_description='Modules for project types',
        )
