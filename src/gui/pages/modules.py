import json

from PySide6.QtGui import Qt, QPixmap, QIcon
from PySide6.QtWidgets import QLabel, QWidget, QTextEdit, QSizePolicy, QTreeWidgetItem

from src.gui.config import ConfigDBTree, ConfigFields, ConfigJoined, ConfigWidget, CHBoxLayout, \
    ConfigDBItem, CVBoxLayout
from src.gui.widgets import IconButton, find_main_widget, colorize_pixmap
from src.utils import sql
from src.utils.helpers import block_signals


class Page_Module_Settings(ConfigDBTree):
    def __init__(self, parent):
        super().__init__(
            parent=parent,
            table_name='modules',
            query="""
                SELECT
                    name,
                    id,
                    -- COALESCE(json_extract(config, '$.enabled'), 1),
                    folder_id
                FROM modules
                ORDER BY pinned DESC, ordr, name""",
            schema=[
                {
                    'text': 'Modules',
                    'key': 'name',
                    'type': str,
                    'stretch': True,
                },
                {
                    'text': 'id',
                    'key': 'id',
                    'type': int,
                    'visible': False,
                },
            ],
            add_item_options={'title': 'Add module', 'prompt': 'Enter a name for the module:'},
            del_item_options={'title': 'Delete module', 'prompt': 'Are you sure you want to delete this module?'},
            folder_key='modules',
            readonly=False,
            layout_type='vertical',
            tree_header_hidden=True,
            config_widget=Module_Config_Widget(parent=self),
            searchable=True,
            default_item_icon=':/resources/icon-jigsaw-solid.png',
        )
        self.icon_path = ":/resources/icon-jigsaw.png"
        self.try_add_breadcrumb_widget(root_title='Modules')
        self.splitter.setSizes([400, 1000])

    # def load(self, select_id=None, silent_select_id=None, append=False):
    #     super().load(select_id, silent_select_id, append)
    #     col_name_list = ['name', 'id']
    #     data = [('jj', 'dhs787dhus', 16)]
    #     with block_signals(self):
    #         for r, row_data in enumerate(data):
    #             parent_item = self
    #             if self.folder_key is not None:
    #                 folder_id = row_data[-1]
    #                 parent_item = self.tree.folder_items_mapping.get(folder_id) if folder_id else self
    #
    #             if len(row_data) > len(self.schema):
    #                 row_data = row_data[:-1]  # remove folder_id
    #
    #             item = QTreeWidgetItem(parent_item, [str(v) for v in row_data])
    #             field_dict = {col_name_list[i]: row_data[i] for i in range(len(row_data))}
    #             item.setData(0, Qt.UserRole, field_dict)
    #
    #             item.setFlags(item.flags() & ~Qt.ItemIsEditable)
    #
    #             if self.default_item_icon:
    #                 pixmap = colorize_pixmap(QPixmap(self.default_item_icon))
    #                 item.setIcon(0, QIcon(pixmap))

    def on_edited(self):  # !420! #
        self.parent.main.system.modules.load(import_modules=False)
        self.config_widget.widgets[0].load()


class Module_Config_Widget(ConfigJoined):
    def __init__(self, parent):
        super().__init__(parent=parent, layout_type='vertical')
        self.widgets = [
            self.Module_Config_Buttons(parent=self),
            self.Module_Config_Fields(parent=self),
        ]

    class Module_Config_Fields(ConfigFields):
        def __init__(self, parent):
            super().__init__(parent=parent)
            self.schema = [
                {
                    'text': 'Load on startup',
                    'type': bool,
                    'default': True,
                    'row_key': 0,
                },
                {
                    'text': 'Data',
                    'type': str,
                    'default': '',
                    'num_lines': 2,
                    'stretch_x': True,
                    'stretch_y': True,
                    'highlighter': 'PythonHighlighter',
                    'fold_mode': 'python',
                    'monospaced': True,
                    'gen_block_folder_name': 'Generate page',
                    'label_position': None,
                },
            ]

    class Module_Config_Buttons(ConfigWidget):
        def __init__(self, parent):
            super().__init__(parent=parent)
            self.parent = parent
            self.layout = CHBoxLayout(self)
            self.layout.setContentsMargins(0, 2, 0, 2)
            self.icon_size = 19
            self.setFixedHeight(self.icon_size + 6)

            # Label for the status of the module
            self.lbl_status = QLabel(parent=self)
            self.lbl_status.setProperty("class", 'dynamic_color')
            self.lbl_status.setMaximumWidth(450)
            self.lbl_status.setTextInteractionFlags(Qt.TextSelectableByMouse)

            self.btn_reimport = IconButton(
                parent=self,
                icon_path=':/resources/icon-load.png',
                text='Load && run',
                tooltip='Re-import the module and execute it',
                size=self.icon_size,
            )
            self.btn_reimport.clicked.connect(self.reimport)

            self.btn_unload = IconButton(
                parent=self,
                icon_path=':/resources/icon-unload.png',
                text='Unload',
                tooltip='Unload the module',
                size=self.icon_size,
            )
            self.btn_unload.clicked.connect(self.unload)

            self.layout.addWidget(self.lbl_status)
            self.layout.addWidget(self.btn_reimport)
            self.layout.addWidget(self.btn_unload)
            self.layout.addStretch(1)

        def get_item_id(self):  # todo clean
            if hasattr(self.parent.parent, 'get_selected_item_id'):  # todo clean
                return self.parent.parent.get_selected_item_id()
            else:
                return self.parent.parent.item_id

        def load(self):
            from src.system.base import manager
            module_id = self.get_item_id()
            module_metadata = manager.modules.module_metadatas.get(module_id)
            if not module_metadata:
                self.set_status('Unloaded')
                return

            module_hash = module_metadata.get('hash')
            is_loaded = module_id in manager.modules.loaded_module_hashes
            if is_loaded:
                loaded_hash = manager.modules.loaded_module_hashes[module_id]
                is_modified = module_hash != loaded_hash
                if is_modified:
                    self.set_status('Modified')
                else:
                    self.set_status('Loaded')
            else:
                self.set_status('Unloaded')

        def set_status(self, status, text=None):
            if text is None:
                text = status
            status_color_classes = {
                'Loaded': '#6aab73',
                'Unloaded': '#B94343',
                'Modified': '#438BB9',
                'Error': '#B94343',
                'Externally Modified': '#B94343',
            }
            can_reimport = status in ['Modified', 'Unloaded']
            self.btn_reimport.setVisible(can_reimport)
            self.btn_unload.setVisible(status == 'Loaded')
            self.lbl_status.setText(text)
            self.lbl_status.setStyleSheet(f"color: {status_color_classes[status]};")

        def reimport(self):
            module_id = self.get_item_id()
            if not module_id:
                return
            from src.system.base import manager

            module = manager.modules.load_module(module_id)
            if isinstance(module, Exception):
                self.set_status('Error', f"Error: {str(module)}")
            else:
                self.set_status('Loaded')
                if manager.modules.module_folders[module_id] == 'pages':
                    main = find_main_widget(self)
                    main.main_menu.build_custom_pages()
                    main.page_settings.build_schema()  # !! #

        def unload(self):
            module_id = self.get_item_id()
            if not module_id:
                return
            from src.system.base import manager

            manager.modules.unload_module(module_id)
            self.set_status('Unloaded')
            if manager.modules.module_folders[module_id] == 'pages':
                main = find_main_widget(self)
                main.main_menu.build_custom_pages()
                main.page_settings.build_schema()  # !! #


class PageEditor(ConfigWidget):
    def __init__(self, main, module_id):
        super().__init__(parent=main)

        self.main = main
        self.layout = CVBoxLayout(self)  # contains a titlebar (title, close button) and a module config widget
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setFixedWidth(500)

        # create title bar with title and close button
        self.titlebar = QWidget(parent=self)
        self.titlebar_layout = CHBoxLayout(self.titlebar)
        self.titlebar_layout.setContentsMargins(4, 4, 4, 4)
        self.lbl_title = QLabel(parent=self.titlebar)
        self.lbl_title.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        font = self.lbl_title.font()
        font.setBold(True)
        self.lbl_title.setFont(font)
        self.titlebar_layout.addWidget(self.lbl_title)
        self.btn_close = IconButton(parent=self.titlebar, icon_path=':/resources/close.png', size=22)
        self.btn_close.clicked.connect(self.close)
        self.titlebar_layout.addWidget(self.btn_close)

        self.layout.addWidget(self.titlebar)

        # self.module_id = module_id
        self.config_widget = self.PageEditorWidget(parent=self, module_id=module_id)
        self.config_widget.build_schema()
        self.layout.addWidget(self.config_widget)

        self.setFixedHeight(self.main.height())

        from src.system.base import manager
        module_manager = manager.get_manager('modules')
        page_name = module_manager.module_names.get(module_id, None)
        if not page_name:
            return
        self.lbl_title.setText(f'Editing module > {page_name}')

    def close(self):
        self.hide()

    def showEvent(self, event):
        # SHOW THE POPUP TO THE LEFT HAND SIDE OF THE MAIN WINDOW, MINUS 350
        top_left = self.main.rect().topLeft()
        top_left_global = self.main.mapToGlobal(top_left)
        top_left_global.setX(top_left_global.x() - self.width())
        self.move(top_left_global)
        super().showEvent(event)

    def load(self):
        self.config_widget.load()

    class PageEditorWidget(ConfigDBItem):
        def __init__(self, parent, module_id):
            super().__init__(
                parent=parent,
                table_name='modules',
                item_id=module_id,
                config_widget=Module_Config_Widget(parent=self)
            )
            # self.build_schema()
            self.code_ast = None

        def after_init(self):
            pass

        def load(self):
            super().load()
            # load code ast
            module_code = self.config.get('data', None)
            pass

        def on_edited(self):
            from src.system.base import manager
            manager.modules.load(import_modules=False)
            self.config_widget.widgets[0].load()
            # main = find_main_widget(self)
            # main.main_menu.build_custom_pages()
            # main.page_settings.build_schema()  # !! #



def change_widget_type(module, class_id):
    pass