import json

from PySide6.QtWidgets import *
from PySide6.QtGui import QFont, Qt, QCursor
from typing_extensions import override

from utils.helpers import block_signals, set_module_type

from gui import system
from gui.util import find_attribute, find_main, IconButton, CVBoxLayout, CHBoxLayout, ToggleIconButton
from utils import sql

from gui.widgets.config_collection import ConfigCollection


@set_module_type('Widgets')
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
    ]

    def __init__(
        self,
        parent,
        align_left=False,
        right_to_left=False,
        bottom_to_top=False,
        button_kwargs=None,
        default_page=None,
    ):
        super().__init__(parent=parent)
        self.layout = CVBoxLayout(self)
        self.content = QStackedWidget(self)
        self.default_page = default_page
        self.align_left = align_left
        self.right_to_left = right_to_left
        self.bottom_to_top = bottom_to_top
        self.button_kwargs = button_kwargs
        self.content.currentChanged.connect(self.on_current_changed)
        self.settings_sidebar = None
        # self.settings_sidebar = self.ConfigSidebarWidget(parent=self)
        # self.settings_sidebar.setContentsMargins(4,0,0,4)

    @override
    def build_schema(self):
        """Build the widgets of all pages from `self.pages`"""
        # # self.blockSignals(True)
        # page_selections = get_selected_pages(self)

        # Clear the main layout to prevent stacking
        # clear_layout(self.layout)

        # remove all widgets from the content stack
        for i in reversed(range(self.content.count())):
            remove_widget = self.content.widget(i)
            if remove_widget not in self.pages.values():
                self.content.removeWidget(remove_widget)
                remove_widget.deleteLater()

        # # remove settings sidebar
        # if getattr(self, 'settings_sidebar', None):
        #     self.layout.removeWidget(self.settings_sidebar)
        #     self.settings_sidebar.deleteLater()

        # if getattr(self, 'content_container', None):
        #     self.layout.removeWidget(self.content_container)
        #     self.content_container.deleteLater()
        #     self.content_container = None

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

        if self.settings_sidebar is None:
            self.settings_sidebar = self.ConfigSidebarWidget(parent=self)
            self.settings_sidebar.setContentsMargins(4,0,0,4)

            self.content_container = QWidget(self)
            layout = CHBoxLayout(self.content_container)
            if not self.right_to_left:
                layout.addWidget(self.settings_sidebar)
                layout.addWidget(self.content)
            else:
                layout.addWidget(self.content)
                layout.addWidget(self.settings_sidebar)

            self.layout.addWidget(self.content_container)

        else:
            self.settings_sidebar.load()

        # self.settings_sidebar.load()

        # if page_selections:
        #     set_selected_pages(self, page_selections)
        # #     pass

        # if hasattr(self, 'after_init'):
        if hasattr(self, 'after_init'):
            self.after_init()
    
    def after_init(self):
        if self.default_page:
            default_page = self.pages.get(self.default_page)
            page_index = self.content.indexOf(default_page)
            self.content.setCurrentIndex(page_index)

    def get(self, page_name, default=None):
        """Get a page by its name."""
        return self.pages.get(page_name, default)

    def load_page(self, page_name):
        """Load a specific page by its name."""
        page = self.get(page_name)
        if page:
            if hasattr(page, 'load'):
                page.load()

    def goto_page(self, page_name):
        is_current = self.content.currentWidget() == self.pages[page_name]
        if is_current:
            return
        click_button = self.settings_sidebar.page_buttons.get(page_name)
        if click_button:
            click_button.click()

    def on_current_changed(self, _):
        self.load()
        self.update_breadcrumbs()

    class ConfigSidebarWidget(QWidget):
        def __init__(self, parent):
            super().__init__(parent=parent)

            self.parent = parent
            self.main = find_main()
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
            # Update or create new_page_btn
            size = self.button_kwargs.get('icon_size', 25)
            if getattr(self, 'new_page_btn', None) is None:
                self.new_page_btn = IconButton(
                    parent=self,
                    icon_path=None,
                    hover_icon_path=':/resources/icon-new-large.png',
                    size=size,
                )
                self.new_page_btn.setMinimumWidth(25)
                self.new_page_btn.clicked.connect(self.parent.add_page)

                if self.button_type == 'text':
                    self.new_page_btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
                    self.new_page_btn.setMaximumSize(16777215, size)  # Remove width constraint
                    self.new_page_btn.setMinimumHeight(size)
                else:
                    self.new_page_btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)

            pages = self.parent.pages
            if self.parent.bottom_to_top:
                pages = {key: pages[key] for key in reversed(pages.keys())}

            # Update existing buttons or create new ones
            if not hasattr(self, 'page_buttons'):
                self.page_buttons = {}

            # Remove buttons for pages that no longer exist
            for key in list(self.page_buttons.keys()):
                if key not in pages:
                    btn = self.page_buttons.pop(key)
                    if hasattr(self, 'button_group') and self.button_group:
                        self.button_group.removeButton(btn)
                    self.layout.removeWidget(btn)
                    btn.deleteLater()

            # Create or update buttons for current pages
            if self.button_type == 'icon':
                for key, page in pages.items():
                    if key not in self.page_buttons:
                        btn = ToggleIconButton(
                            parent=self,
                            icon_path=getattr(page, 'icon_path', ':/resources/icon-pages-large.png'),
                            size=size,
                            tooltip=getattr(page, 'display_name', key),
                            icon_path_checked=getattr(page, 'icon_path_checked', None),
                            target_when_checked=getattr(page, 'target_when_checked', None),
                            show_checked_background=getattr(page, 'show_checked_background', True),
                            checkable=True,
                        )
                        btn.setFixedSize(size, size)
                        btn.setCheckable(True)
                        self.page_buttons[key] = btn
                    else:
                        # Update existing button properties
                        btn = self.page_buttons[key]
                        btn.setToolTip(getattr(page, 'display_name', key))

            elif self.button_type == 'text':
                for key, page in pages.items():
                    if key not in self.page_buttons:
                        btn = self.Settings_SideBar_Button(
                            parent=self,
                            text=getattr(page, 'display_name', key),
                            **self.button_kwargs,
                        )
                        self.page_buttons[key] = btn
                    else:
                        # Update existing button text
                        btn = self.page_buttons[key]
                        btn.setText(getattr(page, 'display_name', key))

            # Update button group
            if self.button_group is None:
                self.button_group = QButtonGroup(self)
                self.button_group.buttonClicked.connect(self.on_button_clicked)
            else:
                # Clear existing button group
                for btn in self.button_group.buttons():
                    self.button_group.removeButton(btn)

            # Check if layout order already matches
            current_order = []
            for idx in range(self.layout.count()):
                w = self.layout.itemAt(idx).widget()
                if w and w in self.page_buttons.values():
                    current_order.append(w)
            desired_order = [self.page_buttons[key] for key in pages if key in self.page_buttons]
            layout_matches = current_order == desired_order

            if not layout_matches:
                # Reorganize layout
                while self.layout.count():
                    item = self.layout.takeAt(0)
                    if item.widget():
                        item.widget().setParent(None)

                if self.parent.bottom_to_top:
                    self.layout.addStretch(1)
                    self.layout.addWidget(self.new_page_btn)

                for i, (key, page) in enumerate(pages.items()):
                    btn = self.page_buttons[key]
                    btn.setContextMenuPolicy(Qt.CustomContextMenu)
                    btn.customContextMenuRequested.connect(lambda pos, btn=btn: self.show_context_menu(pos, btn))
                    self.button_group.addButton(btn, i)
                    self.layout.addWidget(btn)

                if not self.parent.bottom_to_top:
                    self.layout.addWidget(self.new_page_btn)
                    self.layout.addStretch(1)
            else:
                # Just ensure button group is up to date
                for i, (key, page) in enumerate(pages.items()):
                    btn = self.page_buttons[key]
                    self.button_group.addButton(btn, i)

        def show_context_menu(self, pos, button):
            menu = QMenu(self)

            pages_data = system.manager.modules.get_modules_in_folder('Pages', fetch_keys=('name', 'baked'))
            page_key = next((key for key, value in self.page_buttons.items() if value == button), None)
            if page_key is None:
                return
            is_custom_page = page_key in [p[0] for p in pages_data]
            is_non_baked = any(p[0] == page_key and p[1] == 0 for p in pages_data)

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

            if is_custom_page:
                btn_disable = menu.addAction('Disable')
                btn_disable.triggered.connect(lambda: self.disable_page(page_key))

            if is_non_baked or find_attribute(self.parent, 'user_editing', False):
                btn_delete = menu.addAction('Delete')
                btn_delete.triggered.connect(lambda: self.parent.delete_page(page_key))

            menu.exec_(QCursor.pos())

        def disable_page(self, page_name):
            sql.execute("""
                UPDATE modules SET config = json_set(config, '$.enabled', 0)
                WHERE name = ?
            """, (page_name,))
            system.manager.load()
            self.main.main_pages.build_schema()
            if 'settings' in self.main.main_pages.pages:
                self.main.main_pages.pages['settings'].build_schema()

        def toggle_page_pin(self, page_name, pinned):
            pinned_pages = sql.get_scalar("SELECT `value` FROM settings WHERE `field` = 'pinned_pages';")
            pinned_pages = set(json.loads(pinned_pages) if pinned_pages else [])

            if pinned:
                pinned_pages.add(page_name)
            elif page_name in pinned_pages:
                pinned_pages.remove(page_name)
            sql.execute("""UPDATE settings SET value = json(?) WHERE `field` = 'pinned_pages';""",
                        (json.dumps(list(pinned_pages)),))

            system.manager.config.load()
            app_config = system.manager.config
            self.main.main_pages.pages['settings'].load_config(app_config)
            # self.load()  # load this sidebar

        def pin_page(self, page_name):
            """Always called from page_settings.sidebar_menu"""
            self.toggle_page_pin(page_name, pinned=True)

            current_page = self.parent.content.currentWidget()
            pinning_page = self.parent.pages[page_name]
            is_current = current_page == pinning_page

            self.main.main_pages.build_schema()
            self.main.main_pages.pages['settings'].build_schema()

            if is_current:
                self.main.main_pages.goto_page(page_name)

        def unpin_page(self, page_name):
            """Always called from main_pages.sidebar_menu"""
            self.toggle_page_pin(page_name, pinned=False)

            current_page = self.parent.content.currentWidget()
            unpinning_page = self.parent.pages[page_name]
            is_current = current_page == unpinning_page

            # # if current page is the one being unpinned, switch to the system page, then switch to the unpinned page
            self.main.main_pages.build_schema()
            self.main.main_pages.pages['settings'].build_schema()

            if is_current:
                self.parent.goto_page('settings')
                self.main.main_pages.pages['settings'].goto_page(page_name)

        def on_button_clicked(self, button):
            button_index = self.button_group.id(button)
            current_index = self.parent.content.currentIndex()
            if self.parent.bottom_to_top:
                button_group_count = self.button_group.buttons().__len__()
                button_index = button_group_count - 1 - button_index

            if button_index == current_index:
                page_object = self.parent.content.widget(button_index)
                checked_target = getattr(page_object, 'target_when_checked', None)
                if checked_target:
                    if callable(checked_target):
                        checked_target()
            else:
                self.parent.content.setCurrentIndex(button_index)

            self.parent.update_page_map()
            
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