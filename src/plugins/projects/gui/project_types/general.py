from PySide6.QtWidgets import QPushButton

from gui.util import find_ancestor_tree_item_id, find_main
from gui.widgets.config_db_tree import ConfigDBTree
from gui.widgets.config_fields import ConfigFields
from gui.widgets.config_joined import ConfigJoined
from gui.widgets.config_json_tree import ConfigJsonTree
from gui.widgets.config_tabs import ConfigTabs
from gui.widgets.file_tree import FileTree
from plugins.workflows.widgets.chat_widget import ChattableWorkflowWidget
from utils.helpers import display_message, get_entity_workflow_config
from utils.reset import run_bake_block_maps


class GeneralProject(ConfigJoined):
    def __init__(self, parent):
        super().__init__(
            parent=parent,
            resizable=True,
            propagate_config=True,
            widgets=[
                self.Project_Fields(parent=self),
                self.Project_Config_Files(parent=self),
                self.Project_Bottom_Tabs(parent=self),
            ],
        )
    
    def update_config(self):
        super().update_config()
        pass

    class Project_Fields(ConfigFields):
        def __init__(self, parent):
            super().__init__(
                parent=parent,
                schema=[
                    {
                        'text': 'Path',
                        'key': 'working_dir',
                        'type': 'file_picker',
                        'mode': 'directory',
                        'row_key': 0,
                    },
                    {
                        'key': '_PROJECT_TYPE',
                        'text': 'Project type',
                        'type': 'project_type_menu',
                        'label_position': None,
                        # 'visibility_predicate': self.member_type_visibility_predicate,
                        'default': '',
                        'row_key': 0,
                    },
                ]
            )
            self.setFixedHeight(35)
        
    class Project_Config_Files(FileTree):
        def __init__(self, parent):
            super().__init__(
                parent=parent, 
                files_in_tree=True,
                root_directory='/home/jb/CursorProjects/AgentPilot',
                show_bookmarks=False,
            )

        def load_config(self, json_config=None):
            config = self.parent.get_config()
            path = config.get('working_dir', '')
            self.set_root_directory(path)

    class Project_Bottom_Tabs(ConfigTabs):
        def __init__(self, parent):
            super().__init__(
                parent=parent,
                pages={
                    'Chat': self.Project_Tasks_Tree(parent=self),
                    'Block Maps': self.Block_Maps(parent=self),
                }
            )

        class Project_Tasks_Tree(ConfigDBTree):
            def __init__(self, parent):
                super().__init__(
                    parent=parent,
                    table_name='contexts',
                    layout_type='horizontal',
                    query="""
                        SELECT
                            name,
                            id,
                            folder_id
                        FROM contexts
                        WHERE kind = :kind
                        ORDER BY id DESC
                    """,
                    kind=lambda: f'PROJECT:{find_ancestor_tree_item_id(parent)}',
                    folder_key=lambda: f'project:{find_ancestor_tree_item_id(parent)}:task',
                    schema=[
                        {
                            'text': 'Tasks',
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
                    config_widget=self.Project_Chat_Widget(parent=self),
                )

            def add_item(self):
                from gui import system

                kind = self.kind
                if callable(kind):
                    kind = kind()
                existing_id = self.db_connector.get_scalar("""
                    SELECT c.id FROM contexts c
                    WHERE c.kind = ? AND c.name = ''
                        AND NOT EXISTS (
                            SELECT 1 FROM contexts_messages m
                            WHERE m.context_id = c.id
                        )
                    LIMIT 1""",
                    (kind,),
                )
                if existing_id:
                    self.load(select_id=existing_id)
                    return

                entity_val = system.manager.config.get(
                    'system.default_project_entity', '',
                )
                config = get_entity_workflow_config(entity_val)
                self.manager.add(name='', kind=kind, config=config)
                last_insert_id = self.db_connector.get_scalar(
                    "SELECT seq FROM sqlite_sequence WHERE name=?",
                    (self.table_name,)
                )
                self.load(select_id=last_insert_id)

            class Project_Chat_Widget(ChattableWorkflowWidget):
                def __init__(self, parent):
                    super().__init__(
                        parent=parent,
                        kind='PROJECT',
                        workflow_editable=False,
                    )

                def load_config(self, json_config=None):
                    project_id = find_ancestor_tree_item_id(self.parent)
                    self.kind = f'PROJECT:{project_id}'
                    super().load_config(json_config)

        class Block_Maps(ConfigJoined):
            def __init__(self, parent):
                super().__init__(
                    parent=parent,
                    widgets=[
                        self.Block_Maps_Tree(parent=self),
                    ]
                )

            def after_init(self):
                self.bake_btn = QPushButton('Bake')
                self.bake_btn.clicked.connect(self.on_bake)
                self.layout.addWidget(self.bake_btn)

            def on_bake(self):
                config = self.parent.parent.get_config()
                run_bake_block_maps(
                    config,
                    self.bake_btn,
                    finished_callback=self._refresh_file_tree,
                )

            def _refresh_file_tree(self):
                file_tree = self.parent.parent.widgets[1]
                file_tree._clear_caches()
                file_tree.file_view.refresh()
                root_path = str(file_tree.root_directory)
                file_tree.nav_panel.dir_model.setRootPath('')
                file_tree.nav_panel.dir_model.setRootPath(root_path)

            class Block_Maps_Tree(ConfigJsonTree):
                def __init__(self, parent):
                    super().__init__(
                        parent=parent,
                        conf_namespace='block_maps',
                        schema=[
                            {
                                'text': 'Block',
                                'key': 'block',
                                'type': 'entity',
                                'entity_table': 'blocks',
                                'stretch': True,
                            },
                            {
                                'text': 'Path',
                                'key': 'path',
                                'type': str,
                                'stretch': True,
                            },
                        ],
                    )

                def set_height(self):
                    pass