
import json
import os

from PySide6.QtWidgets import QFileDialog, QMessageBox
from typing_extensions import override

from src.gui.widgets.config_db_tree import ConfigDBTree
from src.gui.widgets.config_fields import ConfigFields
from src.gui.widgets.config_json_tree import ConfigJsonTree
from src.gui.widgets.config_tabs import ConfigTabs
from src.gui.widgets.config_pages import ConfigPages
from src.gui.widgets.config_joined import ConfigJoined
from src.gui.widgets.config_plugin import ConfigPlugin

from src.gui.util import find_main_widget
from src.utils import sql
from src.utils.sql import define_table
from src.utils.helpers import block_pin_mode, display_message

from src.system import manager

class Page_Settings(ConfigPages):
    display_name = 'Settings'
    icon_path = ":/resources/icon-settings.png"
    page_type = 'main'  # either 'settings', 'main', or 'any' ('any' means it can be pinned between main and settings)
    # include_in_breadcrumbs = True

    def __init__(self, parent):
        super().__init__(parent=parent)
        self.main = find_main_widget(self)

        self.data_source = {
            'table_name': 'settings',
            'data_column': 'value',
            'lookup_column': 'field',
            'lookup_value': 'app_config',
        }

    def on_edited(self):
        from src.system import manager
        manager.config.load()

    @override
    def build_schema(self):
        pinned_pages: list = sql.get_scalar(
            "SELECT `value` FROM settings WHERE `field` = 'pinned_pages';",
            load_json=True
        )
        from src.system import manager
        page_definitions = manager.modules.get_modules_in_folder(
            module_type='Pages',
            fetch_keys=('uuid', 'name', 'class',),
        )
        page_definitions = [  # filter out pages that are not main or pinned
            (module_id, module_name, page_class) for module_id, module_name, page_class in page_definitions
            if getattr(page_class, 'page_type', 'any') == 'settings'
            or (getattr(page_class, 'page_type', 'any') == 'any' and module_name not in pinned_pages)
        ]
        preferred_order = ['system', 'display', 'models', 'roles', 'blocks', 'tools', 'modules']
        # locked_above = ['settings']
        # locked_below = ['chat', 'contexts', 'agents', 'blocks', 'tools', 'modules']
        order_column = 1
        if preferred_order:
            order_idx = {name: i for i, name in enumerate(preferred_order)}
            page_definitions.sort(key=lambda x: order_idx.get(x[order_column], len(preferred_order)))

        new_pages = {}
        # for page_name in locked_above:
        #     new_pages[page_name] = self.pages[page_name]
        for module_id, module_name, page_class in page_definitions:
            try:
                new_pages[module_name] = page_class(parent=self)  # .parent)
                setattr(new_pages[module_name], 'module_id', module_id)
                # setattr(self.pages[module_name], 'propagate', False)
                existing_page = self.pages.get(module_name, None)
                if existing_page and getattr(existing_page, 'user_editing', False):
                    setattr(new_pages[module_name], 'user_editing', True)

                # if hasattr(new_pages[module_name], 'add_breadcrumb_widget'):
                #     new_pages[module_name].add_breadcrumb_widget()

            except Exception as e:
                display_message(self, f"Error loading page '{module_name}':\n{e}", 'Error', QMessageBox.Warning)

        # for page_name in locked_below:
        #     new_pages[page_name] = self.pages[page_name]
        self.pages = new_pages
        # order_column = 1
        # if preferred_order:
        #     order_idx = {name: i for i, name in enumerate(preferred_order)}
        #     page_definitions.sort(key=lambda x: order_idx.get(x[order_column], len(preferred_order)))
        #
        # for module_id, module_name, page_class in page_definitions:
        #     try:
        #         self.pages[module_name] = page_class(parent=self)  # .parent)
        #         setattr(self.pages[module_name], 'module_id', module_id)
        #         # setattr(self.pages[module_name], 'propagate', False)
        #         existing_page = self.pages.get(module_name, None)
        #         if existing_page and getattr(existing_page, 'user_editing', False):
        #             setattr(self.pages[module_name], 'user_editing', True)
        #
        #     except Exception as e:
        #         display_message(self, f"Error loading page '{module_name}':\n{e}", 'Error', QMessageBox.Warning)

        super().build_schema()

    class Page_Todo_Settings(ConfigDBTree):
        def __init__(self, parent):
            define_table('todo')
            super().__init__(
                parent=parent,
                table_name='todo',
                query="""
                    SELECT
                        name,
                        id,
                        COALESCE(json_extract(config, '$.priority'), 'Normal') AS priority,
                        folder_id
                    FROM todo
                    ORDER BY 
                        CASE 
                            WHEN priority = 'High' THEN 1
                            WHEN priority = 'Normal' THEN 2
                            WHEN priority = 'Low' THEN 3
                            ELSE 4
                        END""",
                schema=[
                    {
                        'text': 'Item',
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
                    {
                        'text': 'Priority',
                        'key': 'priority',
                        'type': ('High','Normal','Low',),  # , 'Prompt based',),
                        'is_config_field': True,
                        'change_callback': self.load,
                        # 'reload_on_change': True,
                        'width': 125,
                    },
                ],
                add_item_options={'title': 'Add to-do', 'prompt': 'Enter a name for the item:'},
                del_item_options={'title': 'Delete to-do', 'prompt': 'Are you sure you want to delete this item?'},
                folder_key='todo',
                readonly=False,
                layout_type='vertical',
                tree_header_hidden=True,
                config_widget=self.Todo_Config_Widget(parent=self),
                searchable=True,
                default_item_icon=':/resources/icon-tasks-small.png',
            )
            self.icon_path = ":/resources/icon-todo.png"
            self.splitter.setSizes([400, 1000])

        class Todo_Config_Widget(ConfigFields):
            def __init__(self, parent):
                super().__init__(parent=parent)
                self.schema = [
                    # {
                    #     'text': 'Description',
                    #     'type': str,
                    #     'default': '',
                    #     'num_lines': 10,
                    #     'stretch_x': True,
                    #     'stretch_y': True,
                    #     'placeholder': 'Description',
                    #     'gen_block_folder_name': 'todo',
                    #     'label_position': None,
                    # },
                ]

    class Page_Files_Settings(ConfigTabs):
        def __init__(self, parent):
            super().__init__(parent=parent)
            self.IS_DEV_MODE = True
            self.main = find_main_widget(self)
            self.pages = {
                'Filesystem': self.Page_Filesystem(parent=self),
                'Extensions': self.Page_Extensions(parent=self),
                # 'Folders': self.Page_Folders(parent=self),
            }

        class Page_Filesystem(ConfigDBTree):
            def __init__(self, parent):
                super().__init__(
                    parent=parent,
                    table_name='files',
                    query="""
                        SELECT
                            name,
                            id,
                            folder_id
                        FROM files
                        ORDER BY pinned DESC, ordr, name""",
                    schema=[
                        {
                            'text': 'Files',
                            'key': 'file',
                            'type': str,
                            'label_position': None,
                            'stretch': True,
                        },
                        {
                            'text': 'id',
                            'key': 'id',
                            'type': int,
                            'visible': False,
                        },
                    ],
                    add_item_options={'title': 'NA', 'prompt': 'NA'},
                    del_item_options={'title': 'NA', 'prompt': 'NA'},
                    tree_header_hidden=True,
                    readonly=True,
                    layout_type='horizontal',
                    config_widget=self.File_Config_Widget(parent=self),
                    folder_key='filesystem',
                    folders_groupable=True,
                )

            def add_item(self, column_vals=None, icon=None):
                with block_pin_mode():
                    file_dialog = QFileDialog()
                    file_dialog.setFileMode(QFileDialog.ExistingFile)
                    file_dialog.setOption(QFileDialog.ShowDirsOnly, False)
                    file_dialog.setFileMode(QFileDialog.Directory)
                    path, _ = file_dialog.getOpenFileName(None, "Choose Files", "", options=file_dialog.Options())

                if path:
                    self.add_path(path)

            def add_ext_folder(self):
                with block_pin_mode():
                    file_dialog = QFileDialog()
                    file_dialog.setFileMode(QFileDialog.Directory)
                    file_dialog.setOption(QFileDialog.ShowDirsOnly, True)
                    path = file_dialog.getExistingDirectory(self, "Choose Directory", "")
                    if path:
                        self.add_path(path)

            def add_path(self, path):
                base_directory = os.path.dirname(path)
                directories = []
                while base_directory:
                    directories.append(os.path.basename(base_directory))
                    next_directory = os.path.dirname(base_directory)
                    base_directory = next_directory if next_directory != base_directory else None

                directories = reversed(directories)
                parent_id = None
                for directory in directories:
                    parent_id = super().add_folder(directory, parent_id)

                name = os.path.basename(path)
                config = json.dumps({'path': path, })
                sql.execute(f"INSERT INTO `files` (`name`, `folder_id`) VALUES (?, ?)", (name, parent_id,))
                last_insert_id = sql.get_scalar("SELECT seq FROM sqlite_sequence WHERE name=?", (self.table_name,))
                self.load(select_id=last_insert_id)
                return True

            def dragEnterEvent(self, event):
                # Check if the event contains file paths to accept it
                if event.mimeData().hasUrls():
                    event.acceptProposedAction()

            def dragMoveEvent(self, event):
                # Check if the event contains file paths to accept it
                if event.mimeData().hasUrls():
                    event.acceptProposedAction()

            def dropEvent(self, event):
                # Get the list of URLs from the event
                urls = event.mimeData().urls()

                # Extract local paths from the URLs
                paths = [url.toLocalFile() for url in urls]

                for path in paths:
                    self.add_path(path)

                event.acceptProposedAction()

            class File_Config_Widget(ConfigFields):
                def __init__(self, parent):
                    super().__init__(parent=parent)
                    self.label_width = 175
                    self.schema = []

        class Page_Extensions(ConfigDBTree):
            def __init__(self, parent):
                super().__init__(
                    parent=parent,
                    table_name='file_exts',
                    query="""
                        SELECT
                            name,
                            id,
                            folder_id
                        FROM file_exts
                        ORDER BY name""",
                    schema=[
                        {
                            'text': 'Name',
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
                    add_item_options={'title': 'Add extension', 'prompt': "Enter the file extension without the '.' prefix"},
                    del_item_options={'title': 'Delete extension', 'prompt': 'Are you sure you want to delete this extension?'},
                    readonly=False,
                    folder_key='file_exts',
                    layout_type='horizontal',
                    config_widget=self.Extensions_Config_Widget(parent=self),
                )

            def on_edited(self):
                from src.system import manager
                manager.files.load()

            class Extensions_Config_Widget(ConfigFields):
                def __init__(self, parent):
                    super().__init__(parent=parent)
                    self.schema = [
                        {
                            'text': 'Default attachment method',
                            'type': ('Add path to message','Add contents to message','Encode base64',),
                            'default': 'Add path to message',
                            # 'width': 385,
                        },
                    ]

    class Page_VecDB_Settings(ConfigDBTree):
        def __init__(self, parent):
            self.IS_DEV_MODE = True
            super().__init__(
                parent=parent,
                table_name='vectordbs',
                query="""
                    SELECT
                        name,
                        id,
                        folder_id
                    FROM vectordbs
                    ORDER BY pinned DESC, ordr, name""",
                schema=[
                    {
                        'text': 'Name',
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
                add_item_options=('Add VecDB table', 'Enter a name for the table:'),
                del_item_options=('Delete VecDB table', 'Are you sure you want to delete this table?'),
                readonly=False,
                layout_type='horizontal',
                folder_key='vectortable_names',
                config_widget=self.VectorDBConfig(parent=self),
            )

        def on_edited(self):
            from src.system import manager
            manager.vectordbs.load()

        class VectorDBConfig(ConfigPlugin):
            def __init__(self, parent):
                super().__init__(
                    parent,
                    plugin_type='VectorDBSettings',
                    plugin_json_key='vec_db_provider',
                    plugin_label_text='VectorDB provider',
                    none_text='LanceDB'
                )
                self.default_class = self.LanceDB_VecDBConfig

            class LanceDB_VecDBConfig(ConfigTabs):
                def __init__(self, *args, **kwargs):
                    super().__init__(*args, **kwargs)
                    self.pages = {
                        'Config': self.Page_VecDB_Config(parent=self),
                        # 'Test run': self.Page_Run(parent=self),
                    }

                class Page_VecDB_Config(ConfigJoined):
                    def __init__(self, parent):
                        super().__init__(parent=parent, layout_type='horizontal')
                        self.widgets = [
                            # self.Tool_Info_Widget(parent=self),
                            self.Env_Vars_Widget(parent=self),
                        ]

                    # class
                    class Env_Vars_Widget(ConfigJsonTree):
                        def __init__(self, parent):
                            super().__init__(parent=parent,
                                             add_item_options={'title': 'NA', 'prompt': 'NA'},
                                             del_item_options={'title': 'NA', 'prompt': 'NA'})
                            self.parent = parent
                            self.conf_namespace = 'env_vars'
                            self.schema = [
                                {
                                    'text': 'Variable',
                                    'type': str,
                                    'width': 120,
                                    'default': 'Variable name',
                                },
                                {
                                    'text': 'Value',
                                    'type': str,
                                    'stretch': True,
                                    'default': '',
                                },
                            ]

    class Page_Logs_Settings(ConfigDBTree):
        def __init__(self, parent):
            super().__init__(
                parent=parent,
                table_name='logs',
                query="""
                    SELECT
                        name,
                        id,
                        folder_id
                    FROM logs""",
                schema=[
                    {
                        'text': 'Name',
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
                add_item_options=None,
                del_item_options=('Delete Log', 'Are you sure you want to delete this log?'),
                readonly=True,
                layout_type='vertical',
                folder_key='logs',
                config_widget=self.LogConfig(parent=self),
                items_pinnable=False,
            )

        def on_edited(self):
            manager.logs.load()

        class LogConfig(ConfigFields):
            def __init__(self, parent):
                super().__init__(parent=parent)
                self.schema = [
                    {
                        'text': 'Log type',
                        'type': ('File', 'Database', 'API',),
                        'default': 'File',
                    },
                    {
                        'text': 'Log path',
                        'type': str,
                        'default': '',
                    },
                    {
                        'text': 'Log level',
                        'type': ('Debug', 'Info', 'Warning', 'Error', 'Critical',),
                        'default': 'Info',
                    },
                    {
                        'text': 'Log format',
                        'type': str,
                        'default': '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    },
                ]

    class Page_Workspace_Settings(ConfigDBTree):
        def __init__(self, parent):
            self.IS_DEV_MODE = True
            super().__init__(
                parent=parent,
                table_name='workspaces',
                query="""
                    SELECT
                        name,
                        id,
                        folder_id
                    FROM workspaces""",
                schema=[
                    {
                        'text': 'Workspaces',
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
                add_item_options=('Add Workspace', 'Enter a name for the workspace:'),
                del_item_options=('Delete Workspace', 'Are you sure you want to delete this workspace?'),
                readonly=False,
                layout_type='horizontal',
                folder_key='workspaces',
                config_widget=self.WorkspaceConfig(parent=self),
            )

        def on_edited(self):
            from src.system import manager
            manager.workspaces.load()

        class WorkspaceConfig(ConfigFields):
            def __init__(self, parent):
                super().__init__(parent=parent)
                self.schema = [
                    {
                        'text': 'Environment',
                        'type': 'combo',
                        'table_name': 'environments',
                        'fetch_keys': ('name', 'id',),
                        'default': 'Local',
                    },
                ]

    # class Page_Plugin_Settings(ConfigTabs):
    #     def __init__(self, parent):
    #         super().__init__(parent=parent)
    #         self.conf_namespace = 'plugins'
    #
    #         self.pages = {
    #             # 'GPT Pilot': self.Page_Test(parent=self),
    #             # 'CrewAI': Page_Settings_CrewAI(parent=self),
    #             # 'Matrix': Page_Settings_Matrix(parent=self),
    #             'OAI': Page_Settings_OAI(parent=self),
    #             # 'Test Pypi': self.Page_Pypi_Packages(parent=self),
    #         }

    class Page_Sets_Settings(ConfigDBTree):
        def __init__(self, parent):
            # self.IS_DEV_MODE = True
            super().__init__(
                parent=parent,
                table_name='contexts',
                query="""
                    SELECT
                        c.name,
                        c.id,
                        CASE
                            WHEN json_extract(c.config, '$.members') IS NOT NULL THEN
                                CASE
                                    WHEN json_array_length(json_extract(c.config, '$.members')) > 2 THEN
                                        json_array_length(json_extract(c.config, '$.members')) || ' members'
                                    WHEN json_array_length(json_extract(c.config, '$.members')) = 2 THEN
                                        COALESCE(json_extract(json_extract(c.config, '$.members'), '$[1].config."info.name"'), 'Assistant')
                                    WHEN json_extract(json_extract(c.config, '$.members'), '$[1].config._TYPE') = 'agent' THEN
                                        json_extract(json_extract(c.config, '$.members'), '$[1].config."info.name"')
                                    ELSE
                                        json_array_length(json_extract(c.config, '$.members')) || ' members'
                                END
                            ELSE
                                CASE
                                    WHEN json_extract(c.config, '$._TYPE') = 'workflow' THEN
                                        '1 member'
                                    ELSE
                                        COALESCE(json_extract(c.config, '$."info.name"'), 'Assistant')
                                END
                        END as member_count,
                        CASE
                            WHEN json_extract(config, '$._TYPE') = 'workflow' THEN
                                (
                                    SELECT GROUP_CONCAT(json_extract(m.value, '$.config."info.avatar_path"'), '//##//##//')
                                    FROM json_each(json_extract(config, '$.members')) m
                                    WHERE COALESCE(json_extract(m.value, '$.del'), 0) = 0
                                )
                            ELSE
                                COALESCE(json_extract(config, '$."info.avatar_path"'), '')
                        END AS avatar,
                        c.folder_id
                    FROM contexts c
                    LEFT JOIN (
                        SELECT
                            context_id,
                            MAX(id) as latest_message_id
                        FROM contexts_messages
                        GROUP BY context_id
                    ) cmsg ON c.id = cmsg.context_id
                    WHERE c.parent_id IS NULL
                    AND c.kind = 'SET'
                    GROUP BY c.id
                    ORDER BY
                        pinned DESC
                        COALESCE(cmsg.latest_message_id, 0) DESC
                    LIMIT ? OFFSET ?;
                    """,
                schema=[
                    {
                        'text': 'name',
                        'type': str,
                        'image_key': 'avatar',
                        'stretch': True,
                    },
                    {
                        'text': 'id',
                        'key': 'id',
                        'type': int,
                        'visible': False,
                    },
                    {
                        'key': 'member_count',
                        'text': '',
                        'type': str,
                        'width': 100,
                    },
                    {
                        'key': 'avatar',
                        'text': '',
                        'type': str,
                        'visible': False,
                    },
                ],
                kind='SET',
                dynamic_load=True,
                add_item_options=('Add Context', 'Enter a name for the context:'),
                del_item_options=('Delete Context', 'Are you sure you want to permanently delete this context?'),
                layout_type='vertical',
                config_widget=None,
                tree_header_hidden=True,
                folder_key='sets',
                init_select=False,
                filterable=True,
                searchable=True,
                archiveable=True,
            )
