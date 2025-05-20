import json

from PySide6.QtCore import QSize
from PySide6.QtWidgets import *
from PySide6.QtGui import QFont, Qt, QCursor
from typing_extensions import override

from src.utils.helpers import block_signals

from src.gui.util import find_attribute, find_main_widget, clear_layout, IconButton, CVBoxLayout, CHBoxLayout
from src.utils import sql

from src.gui.widgets.config_collection import ConfigCollection


class ConfigPages(ConfigCollection):
    def __init__(
        self,
        parent,
        align_left=False,
        right_to_left=False,
        bottom_to_top=False,
        button_kwargs=None,
        default_page=None,
        is_pin_transmitter=False,
    ):
        super().__init__(parent=parent)
        self.layout = CVBoxLayout(self)
        self.content = QStackedWidget(self)
        # self.user_editable = True
        self.settings_sidebar = None
        self.default_page = default_page
        self.align_left = align_left
        self.right_to_left = right_to_left
        self.bottom_to_top = bottom_to_top
        self.button_kwargs = button_kwargs
        self.is_pin_transmitter = is_pin_transmitter
        self.content.currentChanged.connect(self.on_current_changed)

    @override
    def build_schema(self):
        """Build the widgets of all pages from `self.pages`"""
        # self.blockSignals(True)
        # remove all widgets from the content stack
        for i in reversed(range(self.content.count())):
            remove_widget = self.content.widget(i)
            self.content.removeWidget(remove_widget)
            remove_widget.deleteLater()

        # remove settings sidebar
        if getattr(self, 'settings_sidebar', None):
            self.layout.removeWidget(self.settings_sidebar)
            self.settings_sidebar.deleteLater()

        # hidden_pages = getattr(self, 'hidden_pages', [])  # !! #
        with block_signals(self.content, recurse_children=False):
            for page_name, page in self.pages.items():
                # if page_name in hidden_pages:  # !! #
                #     continue

                if hasattr(page, 'build_schema'):
                    page.build_schema()
                self.content.addWidget(page)

            if self.default_page:
                default_page = self.pages.get(self.default_page)
                page_index = self.content.indexOf(default_page)
                self.content.setCurrentIndex(page_index)

        self.settings_sidebar = self.ConfigSidebarWidget(parent=self)

        layout = CHBoxLayout()
        if not self.right_to_left:
            layout.addWidget(self.settings_sidebar)
            layout.addWidget(self.content)
        else:
            layout.addWidget(self.content)
            layout.addWidget(self.settings_sidebar)

        self.layout.addLayout(layout)

        if hasattr(self, 'after_init'):
            self.after_init()
        # self.blockSignals(False)

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

            self.layout = CVBoxLayout(self)
            self.layout.setContentsMargins(10, 0, 10, 0)
            self.button_group = None
            self.new_page_btn = None

            self.load()

        def load(self):
            class_name = self.parent.__class__.__name__
            skip_count = 3 if class_name == 'MainPages' else 0
            clear_layout(self.layout, skip_count=skip_count)  # for title button bar todo dirty
            self.new_page_btn = None

            pinnable_pages = []  # todo
            pinned_pages = []
            # visible_pages = self.parent.pages

            if self.parent.is_pin_transmitter:
                main = find_main_widget(self)
                pinnable_pages = main.pinnable_pages()  # getattr(self.parent, 'pinnable_pages', [])
                pinned_pages = main.pinned_pages()
                # visible_pages = {key: page for key, page in self.parent.pages.items()}
                #                  # if key not in self.parent.hidden_pages}  # !! #

            if self.button_type == 'icon':
                self.page_buttons = {
                    key: IconButton(
                        parent=self,
                        icon_path=getattr(page, 'icon_path', ':/resources/icon-pages-large.png'),
                        size=self.button_kwargs.get('icon_size', QSize(16, 16)),
                        tooltip=key.title(),
                        checkable=True,
                    ) for key, page in self.parent.pages.items()
                }
                self.page_buttons['Chat'].setObjectName("homebutton")

                for btn in self.page_buttons.values():
                    btn.setCheckable(True)
                visible_pages = {key: page for key, page in self.parent.pages.items()
                                 if key in pinned_pages}

            elif self.button_type == 'text':
                self.page_buttons = {
                    key: self.Settings_SideBar_Button(
                        parent=self,
                        text=key,
                        **self.button_kwargs,
                    ) for key in self.parent.pages.keys()
                }
                visible_pages = {key: page for key, page in self.parent.pages.items()
                                 if key not in pinned_pages}

            self.button_group = QButtonGroup(self)

            if len(self.page_buttons) > 0:
                for page_key, page_btn in self.page_buttons.items():
                    visible = page_key in visible_pages
                    if not visible:
                        page_btn.setVisible(False)

                for page_key, page_btn in self.page_buttons.items():
                    page_btn.setContextMenuPolicy(Qt.CustomContextMenu)
                    page_btn.customContextMenuRequested.connect(lambda pos, btn=page_btn: self.show_context_menu(pos, btn, pinnable_pages))

            for i, (key, btn) in enumerate(self.page_buttons.items()):
                self.button_group.addButton(btn, i)
                self.layout.addWidget(btn)

            if self.parent.__class__.__name__ != 'MainPages':
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

        def show_context_menu(self, pos, button, pinnable_pages):
            menu = QMenu(self)

            from src.system import manager
            custom_pages = manager.modules.get_modules_in_folder('Pages', fetch_keys=('name',))
            page_key = next(key for key, value in self.page_buttons.items() if value == button)
            is_custom_page = page_key in custom_pages
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
        #
        # def rename_page(self, page_name):
        #     pass
        #
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
            # sql.execute("""UPDATE settings SET value = json_set(value, '$."display.pinned_pages"', json(?)) WHERE `field` = 'app_config'""",
            #             (json.dumps(list(pinned_pages)),))
            manager.config.load()
            app_config = manager.config
            self.main.page_settings.load_config(app_config)
            self.load()  # load this sidebar

        def pin_page(self, page_name):
            """Always called from page_settings.sidebar_menu"""
            self.toggle_page_pin(page_name, pinned=True)
            target_widget = self.main.main_menu
            target_widget.settings_sidebar.load()

            # if current page is the one being pinned, switch the page_settings sidebar to the system page, then switch to the pinned page
            self.click_menu_button(target_widget, page_name)

        def unpin_page(self, page_name):
            """Always called from main_pages.sidebar_menu"""
            self.toggle_page_pin(page_name, pinned=False)
            target_widget = self.main.page_settings
            target_widget.settings_sidebar.load()

            # if current page is the one being unpinned, switch to the system page, then switch to the unpinned page
            self.click_menu_button(target_widget, page_name)

        def click_menu_button(self, widget, page_name):
            current_page = self.parent.content.currentWidget()
            unpinning_page = self.parent.pages[page_name]
            if current_page == unpinning_page:
                settings_button = next(iter(self.page_buttons.values()), None)
                settings_button.click()

                click_button = widget.settings_sidebar.page_buttons.get(page_name)
                if click_button:
                    widget.settings_sidebar.on_button_clicked(click_button)


        def on_button_clicked(self, button):
            current_index = self.parent.content.currentIndex()
            clicked_index = self.button_group.id(button)
            if current_index == clicked_index:
                is_main = self.parent.__class__.__name__ == 'MainPages'
                if is_main and button == self.page_buttons.get('Chat'):
                    has_no_messages = len(self.parent.main.page_chat.workflow.message_history.messages) == 0
                    if has_no_messages:
                        return
                    main = find_main_widget(self)
                    copy_context_id = main.page_chat.workflow.context_id
                    main.page_chat.new_context(copy_context_id=copy_context_id)
                    main.page_chat.top_bar.btn_prev_context.setEnabled(True)
                return
            self.parent.content.setCurrentIndex(clicked_index)
            button.setChecked(True)

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