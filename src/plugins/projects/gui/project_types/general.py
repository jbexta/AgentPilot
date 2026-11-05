import json

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import QApplication, QPushButton, QTreeWidgetItem

from gui.style import ACCENT_COLOR_1
from utils.helpers import block_signals

from gui.gui_utils.helpers import colorize_pixmap, find_ancestor_tree_item_id, find_attribute, find_main
from gui.gui_utils.custom_menu import CustomMenu
from gui.widgets.config_db_tree import ConfigDBTree
from gui.widgets.config_fields import ConfigFields
from gui.widgets.config_joined import ConfigJoined
from gui.widgets.config_json_tree import ConfigJsonTree
from gui.widgets.config_tabs import ConfigTabs
from plugins.files.widgets.file_tree import FileTree
from plugins.claude_code.widgets.claude_context import ClaudeContext
from plugins.workflows.widgets.chat_widget import ChattableWorkflowWidget
from plugins.workflows.pages.plans import Page_Plan_Settings
from plugins.workflows.pages.skills import Page_Skill_Settings
from plugins.tasks.pages.tasks import Page_Tasks_Settings
from utils.helpers import display_message
from plugins.workflows.utils.workflows import get_entity_workflow_config
from utils.reset import run_bake_block_maps


class GeneralProject(ConfigJoined):
    def __init__(self, parent):
        super().__init__(
            parent=parent,
            resizable=True,
            propagate_config=True,
            widgets=[
                self.Project_Fields(parent=self),
                self.Project_Side_Tabs(parent=self),
                self.Project_Bottom_Tabs(parent=self),
            ],
        )

    def after_init(self):
        file_preview = self.widgets[1].pages['Files'].file_preview
        file_preview.tab_widget.currentChanged.connect(
            lambda _: self._focus_active_file()
        )

    def _focus_active_file(self):
        file_preview = self.widgets[1].pages['Files'].file_preview
        current = file_preview.tab_widget.currentWidget()
        rel_path = ''
        if current is not None:
            filepath = next(
                (fp for fp, w in file_preview.open_files.items()
                 if w is current),
                None,
            )
            working_dir = (self.get_config().get('working_dir', '') or '').rstrip('/')
            if filepath and working_dir and filepath.startswith(working_dir + '/'):
                rel_path = filepath[len(working_dir) + 1:]
        tasks_tree = self.widgets[2].pages['Chat']
        tasks_tree.focus_file_group(rel_path)

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
                        'stretch_x': True,
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
            self.propagate_config = True
            self.setFixedHeight(35)

    class Project_File_Tree(FileTree):
        def __init__(self, parent):
            super().__init__(
                parent=parent,
                files_in_tree=True,
                root_directory='/home/jb/CursorProjects/AgentPilot',
                show_bookmarks=False,
            )
            self.propagate_config = True

        def load_config(self, json_config=None):
            config = self.parent.parent.get_config()
            path = config.get('working_dir', '')
            self.set_root_directory(path)

        def _add_extra_file_actions(self, menu, file_path):
            action = menu.addAction("Show chats that edited")
            action.triggered.connect(
                lambda: self._show_chats_that_edited(file_path)
            )

        def _show_chats_that_edited(self, file_path):
            working_dir = (
                self.parent.parent.get_config().get('working_dir', '') or ''
            ).rstrip('/')
            fp = str(file_path)
            if working_dir and fp.startswith(working_dir + '/'):
                rel_path = fp[len(working_dir) + 1:]
            else:
                rel_path = fp
            tasks_tree = self.parent.parent.widgets[2].pages['Chat']
            tasks_tree.enter_chats_for_file_mode(rel_path)

    class Project_Side_Tabs(ConfigTabs):
        def __init__(self, parent):
            super().__init__(
                parent=parent,
                pages={
                    'Files': parent.Project_File_Tree(parent=self),
                    'Context': ClaudeContext(self, lambda: self.config.get(
                        'working_dir'), conf_namespace='context'),
                }
            )
            self.propagate_config = True

    class Project_Bottom_Tabs(ConfigTabs):
        def __init__(self, parent):
            super().__init__(
                parent=parent,
                pages={
                    'Chat': self.Project_Tasks_Tree(parent=self),
                    'Todo': self.Project_Typed_Tasks_Tree(parent=self, task_type='Todo', item_name='todo'),
                    'Issues': self.Project_Typed_Tasks_Tree(parent=self, task_type='Issues', item_name='issue'),
                    'Skills': self.Project_Skills_Tree(parent=self),
                    'Blocks': self.Project_Blocks_Tree(parent=self),
                    'Plans': self.Project_Plans_Tree(parent=self),
                }
            )
            self.propagate_config = True
            # Match the tree text size used on other pages
            for page in self.pages.values():
                if hasattr(page, 'tree'):
                    page.tree.setFont(QApplication.font(page.tree))
            # Shown under the Blocks tree, but saved with the project
            self.block_maps = self.Block_Maps(parent=self)
            self.pages['Blocks'].tree_layout.addWidget(self.block_maps)

        def build_schema(self):
            super().build_schema()
            self.block_maps.build_schema()

        def load_config(self, json_config=None):
            super().load_config(json_config)
            self.block_maps.load_config()

        def load(self):
            super().load()
            self.block_maps.load()

        def get_config(self):
            return {**super().get_config(), **self.block_maps.get_config()}

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
                    tree_header_hidden=True,
                    collapsible_tree=True,
                    extra_buttons=[
                        {
                            'text': 'Group by file',
                            'icon_path': ':/resources/icon-files.png',
                            'checkable': True,
                            'target': self._toggle_group_by_file,
                        },
                        {
                            'text': 'Group directories',
                            'icon_path': ':/resources/icon-group.png',
                            'checkable': True,
                            'target': self._toggle_group_dirs,
                            'visibility_predicate': lambda: getattr(
                                self, '_group_by_file', False,
                            ),
                        },
                    ],
                )
                self._group_by_file = False
                self._group_dirs = False
                self._chats_for_file = None

                self.all_chats_btn = QPushButton('« All chats')
                self.all_chats_btn.clicked.connect(self.exit_chats_for_file_mode)
                self.all_chats_btn.hide()
                self.tree_layout.insertWidget(0, self.all_chats_btn)

                self.collapsed_buttons = self.Collapsed_Buttons(parent=self)
                self.config_layout.insertWidget(0, self.collapsed_buttons)
                self.update_collapsed_buttons()

            class Collapsed_Buttons(CustomMenu):
                def __init__(self, parent):
                    super().__init__(parent)
                    self.schema = [
                        {
                            'text': '+',
                            'icon_path': ':/resources/icon-new.png',
                            'tooltip': 'New chat',
                            'target': parent.add_item,
                        },
                        {
                            'text': '<',
                            'icon_path': ':/resources/icon-arrow-left.png',
                            'tooltip': 'Show chats',
                            'target': parent.expand_tree,
                            'visibility_predicate': parent.is_tree_collapsed,
                        },
                    ]
                    self.create_toolbar(parent)

            def is_tree_collapsed(self):
                from gui import system
                return system.manager.config.get(self.tree_collapsed_key, False)

            def update_collapsed_buttons(self):
                self.collapsed_buttons.setVisible(self.is_tree_collapsed())
                self.collapsed_buttons.reload_predicates()

            def on_tree_splitter_moved(self):
                super().on_tree_splitter_moved()
                self.update_collapsed_buttons()

            def expand_tree(self):
                total = sum(self.splitter.sizes())
                self.splitter.setSizes([250, total - 250])
                self.on_tree_splitter_moved()

            def _toggle_group_by_file(self):
                self._group_by_file = not self._group_by_file
                self.tree_buttons.reload_predicates()
                self.load()

            def _toggle_group_dirs(self):
                self._group_dirs = not self._group_dirs
                self.load()

            def enter_chats_for_file_mode(self, rel_path):
                self._chats_for_file = rel_path
                self.all_chats_btn.setText(f'« All chats  (filtered: {rel_path})')
                self.all_chats_btn.show()
                self.load()

            def exit_chats_for_file_mode(self):
                self._chats_for_file = None
                self.all_chats_btn.hide()
                self.load()

            def load(self, *args, **kwargs):
                super().load(*args, **kwargs)
                if not self._group_by_file and self._chats_for_file is None:
                    return

                kind = self.kind() if callable(self.kind) else self.kind
                rows = self.db_connector.get_results(
                    query="""
                        SELECT
                            m.context_id,
                            substr(
                                json_extract(m.msg, '$.input.file_path'),
                                length(json_extract(p.config, '$.working_dir')) + 2
                            ) AS rel_path
                        FROM contexts_messages m
                        JOIN contexts c ON c.id = m.context_id
                        JOIN projects p ON c.kind = 'PROJECT:' || p.id
                        WHERE c.kind = :kind
                          AND m.del = 0
                          AND m.role = 'claude_tool'
                          AND json_extract(m.msg, '$.name')
                              IN ('Edit','Write','MultiEdit','NotebookEdit')
                          AND json_extract(m.msg, '$.input.file_path')
                              LIKE json_extract(p.config, '$.working_dir') || '/%'
                        ORDER BY rel_path
                    """,
                    params={'kind': kind},
                )
                if self._chats_for_file is not None:
                    rows = [r for r in rows if r[1] == self._chats_for_file]
                if not rows:
                    if self._chats_for_file is not None:
                        with block_signals(self.tree):
                            for i in range(self.tree.topLevelItemCount() - 1, -1, -1):
                                self.tree.takeTopLevelItem(i)
                    return

                root = {}
                for ctx_id, rel_path in rows:
                    if not rel_path:
                        continue
                    if self._group_dirs or self._chats_for_file is not None:
                        parts = [rel_path.rsplit('/', 1)[-1]]
                    else:
                        parts = rel_path.split('/')
                    node = root
                    for part in parts[:-1]:
                        node = node.setdefault(part, {})
                    node.setdefault(parts[-1], {}).setdefault('__ctx__', []).append(ctx_id)

                folder_icon = QIcon(colorize_pixmap(
                    QPixmap(':/resources/icon-folder.png'), color=ACCENT_COLOR_1,
                ))

                def build(node, name, parent):
                    is_leaf = '__ctx__' in node
                    item = QTreeWidgetItem(parent, [name, ''])
                    item.setData(0, Qt.UserRole, 'file_group_folder')
                    if not is_leaf or self._group_dirs:
                        item.setIcon(0, folder_icon)
                    for child_name, child in node.items():
                        if child_name != '__ctx__':
                            build(child, child_name, item)
                    for ctx_id in node.get('__ctx__', []):
                        orig = self.tree.items_mapping.get(ctx_id)
                        if orig is None:
                            continue
                        clone = QTreeWidgetItem(
                            item,
                            [orig.text(i) for i in range(self.tree.columnCount())],
                        )
                        clone.setData(0, Qt.UserRole, orig.data(0, Qt.UserRole))
                        clone.setIcon(0, orig.icon(0))

                draft_id = self.db_connector.get_scalar("""
                    SELECT c.id FROM contexts c
                    WHERE c.kind = :kind AND c.name = ''
                      AND NOT EXISTS (
                          SELECT 1 FROM contexts_messages m WHERE m.context_id = c.id
                      )
                    LIMIT 1
                """, {'kind': kind})

                selected_id = self.tree.get_selected_item_id()
                with block_signals(self.tree):
                    # Lift root-level chats so virtual folders sit between
                    # user folders and unfoldered chats. The empty draft
                    # context (no title, no messages) stays at the top.
                    lifted = []
                    i = 0
                    while i < self.tree.topLevelItemCount():
                        top = self.tree.topLevelItem(i)
                        tag = top.data(0, Qt.UserRole)
                        if tag != 'folder' and top.text(1) != str(draft_id or ''):
                            lifted.append(self.tree.takeTopLevelItem(i))
                        else:
                            i += 1
                    for name, child in root.items():
                        build(child, name, self.tree)
                    if self._chats_for_file is None:
                        for item in lifted:
                            self.tree.addTopLevelItem(item)
                        # Taking items out of the tree drops their selection
                        if selected_id is not None:
                            self.tree.select_items_by_id(selected_id, notify=False)
                    else:
                        for i in range(self.tree.topLevelItemCount() - 1, -1, -1):
                            top = self.tree.topLevelItem(i)
                            if top.data(0, Qt.UserRole) != 'file_group_folder':
                                self.tree.takeTopLevelItem(i)

                if self._chats_for_file is not None:
                    for i in range(self.tree.topLevelItemCount()):
                        self._expand_recursive(self.tree.topLevelItem(i))

                if self._chats_for_file is None:
                    project = self.parent.parent
                    if hasattr(project, '_focus_active_file'):
                        project._focus_active_file()

            def focus_file_group(self, rel_path):
                with block_signals(self.tree):
                    self._collapse_all_file_groups()
                    if not rel_path:
                        return
                    if self._group_dirs:
                        parts = [rel_path]
                    else:
                        parts = rel_path.split('/')
                    target = None
                    for i in range(self.tree.topLevelItemCount()):
                        top = self.tree.topLevelItem(i)
                        if top.data(0, Qt.UserRole) != 'file_group_folder':
                            continue
                        target = self._match_file_group(top, parts, 0)
                        if target is not None:
                            break
                    node = target
                    while node is not None and node.data(0, Qt.UserRole) == 'file_group_folder':
                        node.setExpanded(True)
                        node = node.parent()

            def _match_file_group(self, item, parts, idx):
                if item.text(0) != parts[idx]:
                    return None
                if idx == len(parts) - 1:
                    return item
                for i in range(item.childCount()):
                    child = item.child(i)
                    if child.data(0, Qt.UserRole) != 'file_group_folder':
                        continue
                    match = self._match_file_group(child, parts, idx + 1)
                    if match is not None:
                        return match
                return None

            def _expand_recursive(self, item):
                item.setExpanded(True)
                for i in range(item.childCount()):
                    self._expand_recursive(item.child(i))

            def _collapse_all_file_groups(self):
                stack = [
                    self.tree.topLevelItem(i)
                    for i in range(self.tree.topLevelItemCount())
                ]
                while stack:
                    item = stack.pop()
                    if item.data(0, Qt.UserRole) != 'file_group_folder':
                        continue
                    item.setExpanded(False)
                    for j in range(item.childCount()):
                        stack.append(item.child(j))

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
                entity_val = system.manager.config.get(
                    'system.default_project_entity', '',
                )
                config = get_entity_workflow_config(entity_val, link=False)

                if existing_id:
                    # The empty draft is reused across sessions, so it can
                    # predate the default entity being set. Seed it, unless
                    # its workflow has already been edited.
                    raw = self.db_connector.get_scalar(
                        "SELECT config FROM contexts WHERE id = ?",
                        (existing_id,),
                    )
                    existing_config = json.loads(raw) if raw else {}
                    if config and not existing_config.get('members'):
                        self.db_connector.execute(
                            "UPDATE contexts SET config = ? WHERE id = ?",
                            (json.dumps(config), existing_id),
                        )
                    self.load(select_id=existing_id)
                    return

                self.manager.add(name='', kind=kind, config=config)
                last_insert_id = self.db_connector.get_scalar(
                    "SELECT seq FROM sqlite_sequence WHERE name=?",
                    (self.table_name,)
                )
                self.load(select_id=last_insert_id)

            def update_name(self):
                pass

            class Project_Chat_Widget(ChattableWorkflowWidget):
                def __init__(self, parent):
                    super().__init__(
                        parent=parent,
                        kind='PROJECT',
                        workflow_editable=False,
                    )

                async def run_workflow_async(self, *args, **kwargs):
                    from plugins.workflows.utils.runs import get_run_manager
                    context_id = self.workflow.context_id
                    on_started = find_attribute(self, 'on_agent_turn_started')
                    if on_started and not get_run_manager().is_running(context_id):
                        on_started()
                    await super().run_workflow_async(*args, **kwargs)
                    on_finished = find_attribute(self, 'on_agent_turn_finished')
                    if on_finished and not get_run_manager().is_running(context_id):
                        on_finished()

                def load_config(self, json_config=None):
                    parent_kind = self.parent.kind
                    if callable(parent_kind):
                        parent_kind = parent_kind()
                    self.kind = parent_kind
                    task_id = self.parent.get_selected_item_id()
                    if task_id is None:
                        super().load_config(json_config)
                        return
                    # ConfigDBTree calls load() right after load_config(), so
                    # bind the workflow here but skip goto_context's auto-load
                    # — otherwise message_collection.load runs twice per click.
                    from plugins.workflows.members.workflow import Workflow
                    from utils import sql
                    prev_workflow = getattr(self, 'workflow', None)
                    if getattr(prev_workflow, 'context_id', None) != task_id:
                        self.restore_scroll_pos = 0  # pin to bottom
                    self.workflow = Workflow(
                        main=self.main, context_id=task_id, chat_widget=self,
                    )
                    self.kind = sql.get_scalar(
                        'SELECT kind FROM contexts WHERE id = ?', (task_id,),
                    )

        class Project_Skills_Tree(ConfigDBTree):
            def __init__(self, parent):
                super().__init__(
                    parent=parent,
                    manager='skills',
                    kind=lambda: f'PROJECT:{find_ancestor_tree_item_id(parent)}',
                    folder_key=lambda: f'project:{find_ancestor_tree_item_id(parent)}:skill',
                    query="""
                        SELECT
                            name,
                            id,
                            uuid,
                            folder_id,
                            parent_id
                        FROM skills
                        WHERE kind = :kind
                        ORDER BY pinned DESC, ordr, name COLLATE NOCASE
                    """,
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
                        {
                            'text': 'uuid',
                            'key': 'uuid',
                            'type': str,
                            'visible': False,
                        },
                    ],
                    readonly=False,
                    layout_type='horizontal',
                    tree_header_hidden=True,
                    default_item_icon=':/resources/icon-block.png',
                    config_widget=Page_Skill_Settings.Skill_Config_Widget(parent=self),
                    folder_config_widget=self.Folder_Config_Widget(parent=self),
                    support_item_nesting=True,
                    searchable=True,
                    collapsible_tree=True,
                )

            # A skill is text (its SKILL.md), not a workflow: edit it exactly
            # like the Skills page does.
            on_item_selected = Page_Skill_Settings.on_item_selected
            save_config = Page_Skill_Settings.save_config
            rename_item = Page_Skill_Settings.rename_item
            _name_for = Page_Skill_Settings._name_for
            _db_config_for = Page_Skill_Settings._db_config_for

            def on_edited(self):
                from gui import system
                system.manager.skills.load()
                system.manager.skills.sync_to_disk()

        class Project_Blocks_Tree(ConfigDBTree):
            def __init__(self, parent):
                super().__init__(
                    parent=parent,
                    manager='blocks',
                    kind=lambda: f'PROJECT:{find_ancestor_tree_item_id(parent)}',
                    folder_key=lambda: f'project:{find_ancestor_tree_item_id(parent)}:block',
                    query="""
                        SELECT
                            name,
                            id,
                            uuid,
                            folder_id,
                            parent_id
                        FROM blocks
                        WHERE kind = :kind
                        ORDER BY pinned DESC, ordr, name COLLATE NOCASE
                    """,
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
                        {
                            'text': 'uuid',
                            'key': 'uuid',
                            'type': str,
                            'visible': False,
                        },
                    ],
                    readonly=False,
                    layout_type='horizontal',
                    tree_header_hidden=True,
                    default_item_icon=':/resources/icon-block.png',
                    config_widget=self.Block_Config_Widget(parent=self),
                    folder_config_widget=self.Folder_Config_Widget(parent=self),
                    support_item_nesting=True,
                    searchable=True,
                    has_chat=True,
                    collapsible_tree=True,
                )

            def load(self, *args, **kwargs):
                super().load(*args, **kwargs)
                self.parent.block_maps.load()

            def reload_current_row(self):
                super().reload_current_row()
                self.parent.block_maps.load()

            class Block_Config_Widget(ChattableWorkflowWidget):
                def __init__(self, parent):
                    super().__init__(
                        parent=parent,
                        kind='BLOCK',
                    )

        class Project_Typed_Tasks_Tree(Page_Tasks_Settings.Page_Scheduled_Tasks):
            # A project's tasks of one type (e.g. `Issues`) have the kind
            # `PROJECT:<id>:<type>`, and are also listed on the Tasks page
            # under the project's folder for that type.
            def __init__(self, parent, task_type, item_name):
                super().__init__(
                    parent=parent,
                    kind=lambda: f'PROJECT:{find_ancestor_tree_item_id(parent)}:{task_type}',
                    folder_key=lambda: f'project:{find_ancestor_tree_item_id(parent)}:{task_type.lower()}:task',
                )
                self.add_item_options = {
                    'title': f'Add {item_name.title()}',
                    'prompt': f'Enter a name for the {item_name}:',
                }

        class Project_Plans_Tree(Page_Plan_Settings):
            # Reuses the standalone Plans page (markdown editor + Claude Code
            # chat assistant + disk sync) scoped to this project via `kind`.
            def __init__(self, parent):
                super().__init__(
                    parent=parent,
                    kind=lambda: f'PROJECT:{find_ancestor_tree_item_id(parent)}',
                    folder_key=lambda: f'project:{find_ancestor_tree_item_id(parent)}:plan',
                )

        class Block_Maps(ConfigJoined):
            def __init__(self, parent):
                super().__init__(
                    parent=parent,
                    propagate_config=True,
                    widgets=[
                        self.Block_Maps_Tree(parent=self),
                    ]
                )

            def on_bake(self):
                config = self.parent.parent.get_config()
                run_bake_block_maps(
                    config,
                    self.widgets[0].tree_buttons.inner_widget.btn_bake,
                    finished_callback=self._refresh_file_tree,
                )

            def _refresh_file_tree(self):
                file_tree = self.parent.parent.widgets[1].pages['Files']
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
                        extra_buttons=[{
                            'text': 'Bake',
                            'target': parent.on_bake,
                        }],
                    )
                    self.propagate_config = True

                def set_height(self):
                    pass