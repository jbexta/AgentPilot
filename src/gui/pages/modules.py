from PySide6.QtCore import QPoint
from PySide6.QtGui import Qt

from src.gui.config import ConfigDBTree, ConfigFields, IconButtonCollection, ConfigJoined, ConfigWidget, CHBoxLayout, \
    ConfigDBItem
from src.gui.widgets import IconButton, find_main_widget

from PySide6.QtWidgets import QLabel


class Page_Module_Settings(ConfigDBTree):
    def __init__(self, parent):
        super().__init__(
            parent=parent,
            db_table='modules',
            query="""
                SELECT
                    name,
                    id,
                    -- COALESCE(json_extract(config, '$.enabled'), 1),
                    folder_id
                FROM modules""",
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
                # {
                #     'text': 'Enabled',
                #     'key': 'enabled',
                #     'type': bool,
                #     'default': '',
                #     'true_value': 'Enabled',
                #     'false_value': 'Disabled',
                #     'is_config_field': True,
                #     'width': 125,
                # },  # !420! #
            ],
            add_item_prompt=('Add module', 'Enter a name for the module:'),
            del_item_prompt=('Delete module', 'Are you sure you want to delete this module?'),
            folder_key='modules',
            readonly=False,
            layout_type='vertical',
            tree_header_hidden=True,
            config_widget=Module_Config_Widget(parent=self),
            # config_buttons=self.ButtonBar(parent=self),
            searchable=True,
            default_item_icon=':/resources/icon-jigsaw-solid.png',
        )
        self.icon_path = ":/resources/icon-jigsaw.png"
        self.try_add_breadcrumb_widget(root_title='Modules')
        self.splitter.setSizes([400, 1000])

    def on_edited(self):  # !420! #
        self.parent.main.system.modules.load(import_modules=False)
        # if getattr(self, 'config_buttons', None):
        #     self.config_buttons.load()
        # if getattr(self, 'config_widget', None):
        self.config_widget.widgets[0].load()
        # self.parent.main.main_menu.build_custom_pages()
        # self.on_item_selected()

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
                    'text': 'Auto-load',
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
                if manager.modules.module_folders[module_id] == 'system_modules.pages':
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
            if manager.modules.module_folders[module_id] == 'system_modules.pages':
                main = find_main_widget(self)
                main.main_menu.build_custom_pages()
                main.page_settings.build_schema()  # !! #


class PopupModule(ConfigDBItem):
    def __init__(self, parent, module_id):
        super().__init__(
            parent=parent,
            db_table='modules',
            item_id=module_id,
            config_widget=Module_Config_Widget(parent=self)
        )

        self.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint)
        self.setFixedWidth(350)
        self.build_schema()

    def showEvent(self, event):
        # SHOW THE POPUP TO THE LEFT HAND SIDE OF THE MAIN WINDOW, MINUS 350
        parent = self.parent.parent.parent
        if parent:
            top_left = parent.rect().topLeft()
            top_left_global = parent.mapToGlobal(top_left)
            top_left_global.setX(top_left_global.x() - self.width())
            self.move(top_left_global)
        super().showEvent(event)
