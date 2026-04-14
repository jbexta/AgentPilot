from PySide6.QtWidgets import *
from PySide6.QtCore import *
from PySide6.QtGui import *

from gui.widgets.file_tree import FileTree
from utils.helpers import set_module_type


@set_module_type('Pages')
class Page_Files(FileTree):
    display_name = 'Files'
    icon_path = ":/resources/icon-files.png"
    page_type = 'any'

    def __init__(self, parent):
        super().__init__(
            parent=parent, 
            files_in_tree=False,
        )