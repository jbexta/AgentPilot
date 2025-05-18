from PySide6.QtCore import QRunnable

from src.gui.widgets.config_widget import ConfigWidget
from src.gui.util import find_main_widget


class ConfigAsyncWidget(ConfigWidget):
    def __init__(self, parent):
        super().__init__(parent=parent)
        self.main = find_main_widget(self)

    def load(self):
        load_runnable = self.LoadRunnable(self)
        self.main.threadpool.start(load_runnable)

    class LoadRunnable(QRunnable):
        def __init__(self, parent):
            super().__init__()

        def run(self):
            pass