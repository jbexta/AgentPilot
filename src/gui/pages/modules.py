
from PySide6.QtGui import Qt
from PySide6.QtWidgets import QLabel, QWidget, QSizePolicy

from src.gui.widgets.config_tabs import ConfigTabs
from src.gui.widgets.config_widget import ConfigWidget
from src.gui.widgets.config_db_tree import ConfigDBTree
from src.gui.widgets.config_fields import ConfigFields
from src.gui.widgets.config_joined import ConfigJoined
from src.gui.util import IconButton, find_main_widget, find_ancestor_tree_item_id, CHBoxLayout, CVBoxLayout, \
    save_table_config, ToggleIconButton
from src.utils import sql
from src.utils.helpers import set_module_type


@set_module_type(module_type='Pages')
class Page_Module_Settings(ConfigDBTree):
    display_name = 'Modules'
    icon_path = ":/resources/icon-jigsaw.png"
    page_type = 'any'  # either 'settings', 'main', or 'any' ('any' means it can be pinned between main and settings)

    def __init__(self, parent):
        super().__init__(
            parent=parent,
            table_name='modules',
            manager='modules',
            query="""
                SELECT
                    name,
                    id,
                    locked,
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
                    'key': 'id',
                    'type': int,
                    'visible': False,
                },
                {
                    'key': 'locked',
                    'type': int,
                    'visible': False,
                },
            ],
            add_item_options={'title': 'Add module', 'prompt': 'Enter a name for the module:'},
            del_item_options={'title': 'Delete module', 'prompt': 'Are you sure you want to delete this module?'},
            folder_key='modules',
            readonly=False,
            layout_type='horizontal',
            tree_header_hidden=True,
            config_widget=Module_Config_Widget(parent=self),
            searchable=True,
            default_item_icon=':/resources/icon-jigsaw-solid.png',
        )
        self.splitter.setSizes([400, 1000])

    def bake_item(self):
        item_id = self.get_selected_item_id()
        if not item_id:
            return

        from src.system import manager
        module_id = item_id
        module_type = manager.modules.get(module_id, {}).get('type', None)

class Module_Config_Widget(ConfigJoined):
    def __init__(self, parent):
        super().__init__(parent=parent, layout_type='vertical', resizable=True)
        self.IS_DEV_MODE = True
        self.main = find_main_widget(self)
        self.widgets = [
            self.Module_Config_Widget_2(parent=self),
            self.Module_Config_Fields(parent=self),
            # self.Module_Config_Fields(parent=self),
        ]

    def after_init(self):
        self.splitter.setSizes([200, 700])

    class Module_Config_Widget_2(ConfigJoined):
        def __init__(self, parent):
            super().__init__(parent=parent, layout_type='vertical')
            self.widgets = [
                self.Module_Config_Buttons(parent=self),
                self.Module_Config_Description(parent=self),
            ]

        class Module_Config_Description(ConfigFields):
            def __init__(self, parent):
                super().__init__(parent=parent)
                self.schema = [
                    {
                        'text': 'Description',
                        'type': str,
                        'default': '',
                        'num_lines': 10,
                        'stretch_x': True,
                        'stretch_y': True,
                        'placeholder_text': 'Description',
                        'gen_block_folder_name': 'todo',
                        'label_position': None,
                    },
                ]

        class Module_Config_Buttons(ConfigWidget):
            def __init__(self, parent):
                super().__init__(parent=parent)
                self.parent = parent
                self.layout = CHBoxLayout(self)
                self.layout.setContentsMargins(0, 2, 0, 2)
                self.icon_size = 22
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
                    target=self.reimport,
                    size=self.icon_size,
                )

                self.btn_unload = IconButton(
                    parent=self,
                    icon_path=':/resources/icon-unload.png',
                    text='Unload',
                    tooltip='Unload the module',
                    target=self.unload,
                    size=self.icon_size,
                )

                self.btn_toggle_description = ToggleIconButton(
                    parent=self,
                    icon_path=':/resources/icon-description.png',
                    tooltip='Toggle description',
                    size=self.icon_size,
                )

                self.layout.addWidget(self.lbl_status)
                self.layout.addWidget(self.btn_reimport)
                self.layout.addWidget(self.btn_unload)
                self.layout.addStretch(1)
                self.layout.addWidget(self.btn_toggle_description)

            # def get_item_id(self):  # todo clean
            #     item_id = find_ancestor_tree_item_id(self.parent.parent)
            #     if not item_id:
            #         return self.parent.module_id
            #     return item_id

            def get_item_id(self):
                return self.parent.parent.parent.get_selected_item_id()

            def load(self):
                return

                from src.system import manager
                module_id = self.get_item_id()
                # module_metadata = manager.modules.get_cell(module_id, 'metadata')
                module_metadata = sql.get_scalar('SELECT metadata FROM modules WHERE id = ?',
                                                 (module_id,), load_json=True)
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
                from src.system import manager

                module = manager.modules.load_module(module_id)
                if isinstance(module, Exception):
                    self.set_status('Error', f"Error: {str(module)}")
                else:
                    self.set_status('Loaded')
                    # if manager.modules.module_folders[module_id] == 'pages':
                    if manager.modules.get_cell(module_id, 'type') == 'pages':
                        main = find_main_widget(self)
                        main.main_pages.build_schema()
                        # main.page_settings.build_schema()

            def unload(self):
                module_id = self.get_item_id()
                if not module_id:
                    return
                from src.system import manager

                manager.modules.unload_module(module_id)
                self.set_status('Unloaded')
                # if manager.modules.module_folders[module_id] == 'pages':
                if manager.modules.get_cell(module_id, 'type') == 'pages':
                    main = find_main_widget(self)
                    main.main_pages.build_schema()
                    # main.page_settings.build_schema()

    class Module_Config_Fields(ConfigFields):
        def __init__(self, parent):
            super().__init__(parent=parent)
            self.conf_namespace = 'source'
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
                    'gen_block_folder_name': 'page_module',
                    'label_position': None,
                },
            ]


class PageEditor(ConfigWidget):
    def __init__(self, main, module_id):
        super().__init__(parent=main)

        self.main = main
        self.module_id = module_id
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

        self.config_widget = self.PageEditorWidget(parent=self, module_id=module_id)
        self.config_widget.build_schema()
        self.layout.addWidget(self.config_widget)

        self.setFixedHeight(self.main.height())

        from src.system import manager
        module_manager = manager.modules
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

    class PageEditorWidget(Module_Config_Widget):
        def __init__(self, parent, module_id):
            super().__init__(parent=parent)
            self.module_id = module_id
            self.data_source = {
                'table_name': 'modules',
                'item_id': module_id,
            }
            self.code_ast = None

        # def load(self):
        #     item_id = self.module_id
        #     table_name = self.data_target['table_name']
        #     json_config = json.loads(sql.get_scalar(f"""
        #         SELECT
        #             `config`
        #         FROM `{table_name}`
        #         WHERE id = ?
        #     """, (item_id,)))
        #     if ((table_name == 'entities' or table_name == 'blocks' or table_name == 'tools')
        #             and json_config.get('_TYPE', 'agent') != 'workflow'):
        #         json_config = merge_config_into_workflow_config(json_config)
        #     self.load_config(json_config)
        #     super().load()
        #
        # def update_config(self):
        #     config = self.get_config()
        #
        #     save_table_config(
        #         ref_widget=self,
        #         table_name='modules',
        #         item_id=self.module_id,
        #         value=json.dumps(config),
        #     )
        #
        #     main = find_main_widget(self)
        #     main.system.modules.load(import_modules=False)
        #     self.widgets[0].load()
