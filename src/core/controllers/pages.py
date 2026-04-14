from core.managers.modules import ModulesController
from utils.helpers import convert_to_safe_case


class PagesController(ModulesController):
    def __init__(self, system):
        super().__init__(
            system, 
            module_type='pages', 
            load_to_path='gui.pages',
            class_based=True,
            inherit_from='QWidget',
            description="UI page modules for the application",
            long_description="Pages are QWidget modules that can be composed of Widget modules"
        )

    def initial_content(self, module_name: str):
        safe_name = convert_to_safe_case(module_name).capitalize()
        return f"""
            from gui.util import CVBoxLayout, CHBoxLayout
            from gui.widgets.config_db_tree import ConfigDBTree
            from gui.widgets.config_fields import ConfigFields
            from gui.widgets.config_joined import ConfigJoined
            from gui.widgets.config_json_tree import ConfigJsonTree
            from gui.widgets.config_pages import ConfigPages
            from gui.widgets.config_tabs import ConfigTabs

            class Page_{safe_name}_Settings(ConfigPages):
                display_name = \"\"\"{module_name}\"\"\"
                page_type = 'main'
                icon_path = ':/resources/icon-tasks.png'

                def __init__(self, parent):
                    super().__init__(parent=parent)
                    self.pages = {{}}
        """