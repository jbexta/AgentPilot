from PySide6.QtWidgets import *
from typing_extensions import override



from utils.helpers import block_signals, set_module_type

from gui.util import find_attribute, IconButton, CVBoxLayout

from gui.widgets.config_collection import ConfigCollection


@set_module_type('Widgets')
class ConfigTabs(ConfigCollection):
    def __init__(self, parent, **kwargs):
        super().__init__(parent=parent)
        self.layout = CVBoxLayout(self)
        self.content = QTabWidget(self)
        self.pages = kwargs.get('pages', {})
        self.new_page_btn = None
        # self.user_editable = True
        self.content.currentChanged.connect(self.on_current_changed)
        hide_tab_bar = kwargs.get('hide_tab_bar', False)
        if hide_tab_bar:
            self.content.tabBar().hide()
        
        self.layout.addWidget(self.content)

        self.new_page_btn = IconButton(
            parent=self,
            icon_path=':/resources/icon-new-large.png',
            size=25,
        )
        self.new_page_btn.setMinimumWidth(25)
        self.new_page_btn.clicked.connect(self.add_page)

    @override
    def build_schema(self):
        """Build the widgets of all tabs from `self.tabs`"""
        # remove all tabs
        for i in reversed(range(self.content.count())):
            widget = self.content.widget(i)
            self.content.removeTab(i)
            # widget.deleteLater()
        
        # build all tabs
        with block_signals(self):
            for tab_name, tab in self.pages.items():
                if hasattr(tab, 'build_schema'):
                    tab.build_schema()
                self.content.addTab(tab, tab_name)

        if not find_attribute(self, 'user_editing'):
            self.new_page_btn.hide()
        self.recalculate_new_page_btn_position()

        if hasattr(self, 'after_init'):
            self.after_init()

    @override
    def load(self):
        super().load()
        self.recalculate_new_page_btn_position()

    def on_current_changed(self, _):
        self.load()
        self.update_breadcrumbs()
        self.update_page_map()
        
    def goto_page(self, page_name):
        if page_name not in self.pages:
            print(f'page {page_name} not found in {self.pages}')
            return
        is_current = self.content.currentWidget() == self.pages[page_name]
        if is_current:
            return
        # set tab
        tab_index = list(self.pages.keys()).index(page_name)
        self.content.setCurrentIndex(tab_index)

    # def show_tab_context_menu(self, pos):
    #     tab_index = self.content.tabBar().tabAt(pos)
    #     if tab_index == -1:
    #         return
    #
    #     menu = QMenu(self.parent)
    #
    #     page_key = list(self.pages.keys())[tab_index]
    #     user_editing = find_attribute(self, 'user_editing', False)
    #     if user_editing:
    #         btn_delete = menu.addAction('Delete')
    #         btn_delete.triggered.connect(lambda: self.delete_page(page_key))
    #
    #         menu.exec_(QCursor.pos())  # todo not working why?
    #         # if action == btn_delete:
    #         #     self.delete_page(page_key)

    def recalculate_new_page_btn_position(self):
        if not self.new_page_btn:
            return
        tab_bar = self.content.tabBar()
        pos = tab_bar.mapTo(self, tab_bar.rect().topRight())
        self.new_page_btn.move(pos.x() + 1, pos.y())