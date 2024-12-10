from PySide6.QtGui import QPalette, QColor, Qt

from src.gui.config import ConfigDBTree, ConfigFields, IconButtonCollection
from src.gui.widgets import PythonHighlighter, IconButton, find_main_widget
from src.members.workflow import WorkflowSettings

from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QLabel, QSizePolicy


class Page_Module_Settings(ConfigDBTree):
    def __init__(self, parent):
        super().__init__(
            parent=parent,
            db_table='modules',
            propagate=False,
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
            layout_type=QVBoxLayout,
            tree_header_hidden=True,
            config_widget=self.Module_Config_Widget(parent=self),
            config_buttons=self.ButtonBar(parent=self),
            searchable=True,
            default_item_icon=':/resources/icon-jigsaw-solid.png',
        )
        self.icon_path = ":/resources/icon-jigsaw.png"
        self.try_add_breadcrumb_widget(root_title='Modules')
        self.splitter.setSizes([400, 1000])

    def on_edited(self):  # !420! #
        self.parent.main.system.modules.load(import_modules=False)
        if getattr(self, 'config_buttons', None):
            self.config_buttons.load()
        # self.parent.main.main_menu.build_custom_pages()
        # self.on_item_selected()

    class Module_Config_Widget(ConfigFields):
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
                    'highlighter': PythonHighlighter,
                    'label_position': None,
                },
            ]

    class ButtonBar(IconButtonCollection):
        def __init__(self, parent):
            super().__init__(parent=parent)
            self.parent = parent

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

        def load(self):
            from src.system.base import manager
            module_id = self.parent.get_selected_item_id()
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
            module_id = self.parent.get_selected_item_id()
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

        def unload(self):
            module_id = self.parent.get_selected_item_id()
            if not module_id:
                return
            from src.system.base import manager

            manager.modules.unload_module(module_id)
            self.set_status('Unloaded')
            if manager.modules.module_folders[module_id] == 'system_modules.pages':
                main = find_main_widget(self)
                main.main_menu.build_custom_pages()
