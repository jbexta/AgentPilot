
from gui.util import CVBoxLayout, CHBoxLayout
from gui.widgets.config_db_tree import ConfigDBTree
from gui.widgets.config_fields import ConfigFields
from gui.widgets.config_joined import ConfigJoined
from gui.widgets.config_json_tree import ConfigJsonTree
from gui.widgets.config_pages import ConfigPages
from gui.widgets.config_tabs import ConfigTabs

class Page_Ooo_Settings(ConfigPages):
    display_name = """ooo"""
    page_type = 'main'
    icon_path = ':/resources/icon-tasks.png'

    def __init__(self, parent):
        super().__init__(parent=parent)
        self.pages = {}
