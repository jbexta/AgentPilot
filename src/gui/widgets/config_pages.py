import json

from PySide6.QtCore import QSize
from PySide6.QtWidgets import *
from PySide6.QtGui import QFont, Qt, QCursor
from typing_extensions import override

from src.utils.helpers import block_signals

from src.gui.util import find_attribute, find_main_widget, clear_layout, IconButton, CVBoxLayout, CHBoxLayout, \
    ToggleIconButton
from src.utils import sql

from src.gui.widgets.config_collection import ConfigCollection


class ConfigPages(ConfigCollection):
    param_schema = [
        {
            'text': 'Right to Left',
            'key': 'w_right_to_left',
            'type': bool,
            'default': False,
        },
        {
            'text': 'Bottom to Top',
            'key': 'w_bottom_to_top',
            'type': bool,
            'default': False,
        }
    ],

    def __init__(
        self,
        parent,
        align_left=False,
        right_to_left=False,
        bottom_to_top=False,
        button_kwargs=None,
        # default_page=None,
    ):
        super().__init__(parent=parent)
        self.layout = CVBoxLayout(self)
        self.content = QStackedWidget(self)
        self.settings_sidebar = None
        # self.default_page = default_page
        self.align_left = align_left
        self.right_to_left = right_to_left
        self.bottom_to_top = bottom_to_top
        self.button_kwargs = button_kwargs
        self.content.currentChanged.connect(self.on_current_changed)

    @override
    def build_schema(self):
        """Build the widgets of all pages from `self.pages`"""
        # # self.blockSignals(True)
        # page_selections = get_selected_pages(self)

        # remove all widgets from the content stack
        for i in reversed(range(self.content.count())):
            remove_widget = self.content.widget(i)
            if remove_widget not in self.pages.values():
                self.content.removeWidget(remove_widget)
                remove_widget.deleteLater()

        # remove settings sidebar
        if getattr(self, 'settings_sidebar', None):
            self.layout.removeWidget(self.settings_sidebar)
            self.settings_sidebar.deleteLater()
        # self.layout.removeWidget(self.content)

        with block_signals(self.content, recurse_children=False):  # todo
            for i, (page_name, page) in enumerate(self.pages.items()):
                widget = self.content.widget(i)
                if widget != page:
                    self.content.insertWidget(i, page)

                if hasattr(page, 'build_schema'):
                    page.build_schema()

            # if self.default_page:
            #     default_page = self.pages.get(self.default_page)
            #     page_index = self.content.indexOf(default_page)
            #     self.content.setCurrentIndex(page_index)

        self.settings_sidebar = self.ConfigSidebarWidget(parent=self)
        self.settings_sidebar.setContentsMargins(4,0,0,4)

        layout = CHBoxLayout()
        if not self.right_to_left:
            layout.addWidget(self.settings_sidebar)
            layout.addWidget(self.content)
        else:
            layout.addWidget(self.content)
            layout.addWidget(self.settings_sidebar)

        self.layout.addLayout(layout)

        # if page_selections:
        #     set_selected_pages(self, page_selections)
        #     pass

        # if hasattr(self, 'after_init'):
        self.after_init()

    def get(self, page_name, default=None):
        """Get a page by its name."""
        return self.pages.get(page_name, default)

    def load_page(self, page_name):
        """Load a specific page by its name."""
        page = self.get(page_name)
        if page:
            if hasattr(page, 'load'):
                page.load()

    def on_current_changed(self, _):
        self.load()
        self.update_breadcrumbs()

    class ConfigSidebarWidget(QWidget):
        def __init__(self, parent):  # , width=None):
            super().__init__(parent=parent)

            self.parent = parent
            self.main = find_main_widget(self)
            self.setAttribute(Qt.WA_StyledBackground, True)
            self.setProperty("class", "sidebar")

            self.button_kwargs = parent.button_kwargs or {}
            self.button_type = self.button_kwargs.get('button_type', 'text')
            self.page_buttons = {}

            self.layout = CVBoxLayout(self)
            self.layout.setContentsMargins(10, 0, 10, 0)
            self.button_group = None
            self.new_page_btn = None

            self.load()

        def load(self):
            clear_layout(self.layout)
            self.new_page_btn = None

            if self.parent.bottom_to_top:
                self.layout.addStretch(1)

            pages = self.parent.pages
            if self.parent.bottom_to_top:
                pages = {key: pages[key] for key in reversed(pages.keys())}

            if self.button_type == 'icon':
                self.page_buttons = {
                    key: ToggleIconButton(
                        parent=self,
                        icon_path=getattr(page, 'icon_path', ':/resources/icon-pages-large.png'),
                        size=self.button_kwargs.get('icon_size', QSize(16, 16)),
                        tooltip=getattr(page, 'display_name', key),
                        icon_path_checked=getattr(page, 'icon_path_checked', None),
                        target_when_checked=getattr(page, 'target_when_checked', None),
                        show_checked_background=getattr(page, 'show_checked_background', True),
                        checkable=True,
                    ) for key, page in pages.items()
                }
                # self.page_buttons['Chat'].setObjectName("homebutton")

                for btn in self.page_buttons.values():
                    btn.setCheckable(True)

            elif self.button_type == 'text':
                self.page_buttons = {
                    key: self.Settings_SideBar_Button(
                        parent=self,
                        text=getattr(page, 'display_name', key),
                        **self.button_kwargs,
                    ) for key, page in pages.items()
                }

            self.button_group = QButtonGroup(self)

            if len(self.page_buttons) > 0:
                for page_key, page_btn in self.page_buttons.items():
                    page_btn.setContextMenuPolicy(Qt.CustomContextMenu)
                    page_btn.customContextMenuRequested.connect(lambda pos, btn=page_btn: self.show_context_menu(pos, btn))

                for i, (key, btn) in enumerate(self.page_buttons.items()):
                    self.button_group.addButton(btn, i)
                    self.layout.addWidget(btn)

            # if self.parent.__class__.__name__ != 'MainPages':
            self.new_page_btn = IconButton(
                parent=self,
                icon_path=':/resources/icon-new-large.png',
                size=25,
            )
            if not find_attribute(self.parent, 'user_editing'):
                self.new_page_btn.hide()
            self.new_page_btn.setMinimumWidth(25)
            self.new_page_btn.clicked.connect(self.parent.add_page)
            self.layout.addWidget(self.new_page_btn)

            if not self.parent.bottom_to_top:
                self.layout.addStretch(1)
            self.button_group.buttonClicked.connect(self.on_button_clicked)

        def show_context_menu(self, pos, button):
            menu = QMenu(self)

            from src.system import manager
            custom_pages = manager.modules.get_modules_in_folder('Pages', fetch_keys=('name',))
            page_key = next(key for key, value in self.page_buttons.items() if value == button)
            is_custom_page = page_key in custom_pages

            pinnable_pages = [key for key, value in self.parent.pages.items()
                              if getattr(value, 'page_type', 'any') == 'any']

            if page_key in pinnable_pages:
                if isinstance(button, IconButton):
                    btn_unpin = menu.addAction('Unpin')
                    btn_unpin.triggered.connect(lambda: self.unpin_page(page_key))
                elif isinstance(button, self.Settings_SideBar_Button):
                    btn_pin = menu.addAction('Pin')
                    btn_pin.triggered.connect(lambda: self.pin_page(page_key))

            if is_custom_page:
                btn_edit = menu.addAction('Edit')
                btn_edit.triggered.connect(lambda: self.parent.edit_page(page_key))

            user_editing = find_attribute(self.parent, 'user_editing', False)
            if user_editing:
                btn_delete = menu.addAction('Delete')
                btn_delete.triggered.connect(lambda: self.parent.delete_page(page_key))

            menu.exec_(QCursor.pos())

        def toggle_page_pin(self, page_name, pinned):
            from src.system import manager
            pinned_pages = sql.get_scalar("SELECT `value` FROM settings WHERE `field` = 'pinned_pages';")
            pinned_pages = set(json.loads(pinned_pages) if pinned_pages else [])

            if pinned:
                pinned_pages.add(page_name)
            elif page_name in pinned_pages:
                pinned_pages.remove(page_name)
            sql.execute("""UPDATE settings SET value = json(?) WHERE `field` = 'pinned_pages';""",
                        (json.dumps(list(pinned_pages)),))

            manager.config.load()
            app_config = manager.config
            self.main.page_settings.load_config(app_config)
            self.load()  # load this sidebar

        def pin_page(self, page_name):
            """Always called from page_settings.sidebar_menu"""
            self.toggle_page_pin(page_name, pinned=True)

            current_page = self.parent.content.currentWidget()
            pinning_page = self.parent.pages[page_name]
            is_current = current_page == pinning_page

            self.main.main_pages.build_schema()
            self.main.page_settings.build_schema()

            if is_current:
                self.main.main_pages.settings_sidebar.click_menu_button(page_name)

        def unpin_page(self, page_name):
            """Always called from main_pages.sidebar_menu"""
            self.toggle_page_pin(page_name, pinned=False)

            current_page = self.parent.content.currentWidget()
            unpinning_page = self.parent.pages[page_name]
            is_current = current_page == unpinning_page

            # # if current page is the one being unpinned, switch to the system page, then switch to the unpinned page
            self.main.main_pages.build_schema()
            self.main.page_settings.build_schema()

            if is_current:
                self.click_menu_button('settings')
                self.main.main_pages.settings_sidebar.click_menu_button(page_name)

        def click_menu_button(self, page_name):
            click_button = self.page_buttons.get(page_name)
            if click_button:
                self.on_button_clicked(click_button)

        def on_button_clicked(self, button):
            current_index = self.parent.content.currentIndex()
            current_button = self.button_group.button(current_index)
            clicked_index = self.button_group.id(button)
            if self.parent.bottom_to_top:
                button_group_count = self.button_group.buttons().__len__()
                clicked_index = button_group_count - 1 - clicked_index

            if current_index == clicked_index:
                i = current_index
                page_object = self.parent.content.widget(i)
                checked_target = getattr(page_object, 'target_when_checked', None)
                if checked_target:
                    if callable(checked_target):
                        checked_target()
            else:
                button.setChecked(True)
                button.refresh_icon()
                if current_button:
                    current_button.setChecked(False)
                    current_button.refresh_icon()
                self.parent.content.setCurrentIndex(clicked_index)

        class Settings_SideBar_Button(QPushButton):
            def __init__(self, parent, text='', text_size=13, align_left=False):
                super().__init__()
                self.setText(self.tr(text))  # todo - translate
                self.setCheckable(True)
                self.font = QFont()
                self.font.setPointSize(text_size)
                self.setFont(self.font)
                if align_left:
                    self.setStyleSheet("QPushButton { text-align: left; }")

            def refresh_icon(self):
                pass  # todo clean