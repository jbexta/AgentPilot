import json

from PySide6.QtCore import Qt, QFileSystemWatcher
from PySide6.QtWidgets import QMessageBox

from gui import system
from gui.widgets.config_db_tree import ConfigDBTree
from gui.widgets.config_fields import ConfigFields
from gui.widgets.config_joined import ConfigJoined
from plugins.workflows.widgets.chat_widget import ChattableWorkflowWidget
from utils import sql
from utils.helpers import display_message, get_text


class Page_Plan_Settings(ConfigDBTree):
    display_name = 'Plans'
    icon_path = ":/resources/icon-plan.png"
    page_type = 'any'

    def __init__(self, parent, kind=None, folder_key='plans'):
        # ``kind`` scopes the page to a single project (a 'PROJECT:<id>' value,
        # possibly a lambda). When set, the tree is filtered to that project and
        # new plans inherit the kind. When None (the standalone page), all plans
        # are shown grouped by kind so project plans appear under their project.
        scoped = kind is not None
        if scoped:
            query = """
                SELECT name, id, uuid, folder_id
                FROM plans
                WHERE kind = :kind
                ORDER BY pinned DESC, ordr, name COLLATE NOCASE"""
        else:
            query = """
                SELECT name, id, uuid, folder_id, kind
                FROM plans
                ORDER BY kind, pinned DESC, ordr, name COLLATE NOCASE"""
        super().__init__(
            parent=parent,
            manager='plans',
            kind=kind,
            query=query,
            schema=[
                {'text': 'Name', 'key': 'name', 'type': str, 'stretch': True},
                {'text': 'id', 'key': 'id', 'type': int, 'visible': False},
                {'text': 'uuid', 'key': 'uuid', 'type': str, 'visible': False},
            ],
            readonly=False,
            layout_type='horizontal',
            tree_header_hidden=True,
            default_item_icon=':/resources/icon-description.png',
            config_widget=self.Plan_Config_Widget(parent=self),
            folder_key=folder_key,
            group_by_kind=not scoped,
            searchable=True,
            items_bakeable=False,
        )
        self.splitter.setSizes([400, 1000])

        self._sync_tree_with_disk()
        self._init_watcher()

    # The file is the source of truth — bypass the DB-config plumbing for the body.

    def on_item_selected(self):
        item_id = self.get_selected_item_id()
        if not (item_id and self.config_widget):
            return super().on_item_selected()
        self.toggle_config_widget(config_type='item')
        self.config_widget.maybe_rebuild_schema(self.schema_overrides, item_id)
        name = self._name_for(item_id)
        body = system.manager.plans.read(name) if name else ''
        self.config_widget.load_config({'data': body})
        self.config_widget.load()
        # Point the chat's Claude Code agent at the selected plan and
        # restore (or create) this plan's own conversation.
        if name:
            self.config_widget.chat.load_for_plan(item_id, name)

    def save_config(self):
        item_id = self.get_selected_item_id()
        if item_id is None:
            return
        name = self._name_for(item_id)
        if not name:
            return
        body = self.config_widget.get_config().get('data', '')
        system.manager.plans.write(name, body)

    def rename_item(self):
        item = self.tree.currentItem()
        if not item:
            return
        tag = item.data(0, Qt.UserRole)
        if tag == 'folder':
            return super().rename_item()

        item_id = self.get_selected_item_id()
        if not item_id:
            return
        mgr = system.manager.plans
        old_name = self._name_for(item_id)
        if not old_name:
            return
        old_slug = mgr._slug(old_name)

        current = old_name
        while True:
            text, ok = get_text(
                self, 'Rename plan', 'Enter a new name for the plan:', text=current
            )
            if not ok:
                return
            new_slug = mgr._slug(text)
            if not new_slug:
                display_message(
                    message='Invalid filename. Use letters, numbers, spaces, hyphens or underscores.',
                    icon=QMessageBox.Warning,
                )
                current = text
                continue
            if new_slug == old_slug:
                return
            exists = self.db_connector.get_scalar(
                "SELECT COUNT(*) FROM plans WHERE name = ? AND id != ?", (new_slug, item_id)
            )
            new_path = mgr.path_for(new_slug)
            if exists or (new_path and new_path.exists()):
                display_message(
                    message='A plan with that name already exists.',
                    icon=QMessageBox.Warning,
                )
                current = text
                continue
            old_path = mgr.path_for(old_slug)
            try:
                if old_path and old_path.exists() and new_path:
                    old_path.rename(new_path)
                self.db_connector.execute(
                    "UPDATE plans SET name = ? WHERE id = ?", (new_slug, item_id)
                )
            except OSError as e:
                display_message(
                    message=f'Error renaming file: {e}', icon=QMessageBox.Warning
                )
                return
            self._watch_files()
            self.load()
            return

    # -- tree ↔ disk identity sync ---------------------------------------------

    def _name_for(self, item_id):
        return self.db_connector.get_scalar("SELECT name FROM plans WHERE id = ?", (item_id,))

    def _sync_tree_with_disk(self):
        """Insert DB rows for files that exist on disk but aren't tracked,
        and drop rows whose file no longer exists. Identity only — never
        touches the body.
        """
        mgr = system.manager.plans
        disk = set(mgr.list_files())
        rows = self.db_connector.get_results("SELECT id, name FROM plans") or []
        db = {mgr._slug(name): row_id for row_id, name in rows}
        for slug in disk - db.keys():
            self.db_connector.execute("INSERT INTO plans (name) VALUES (?)", (slug,))
        for slug in db.keys() - disk:
            self.db_connector.execute("DELETE FROM plans WHERE id = ?", (db[slug],))

    # -- live watcher ----------------------------------------------------------

    def _init_watcher(self):
        plans_dir = system.manager.plans.PLANS_DIR
        plans_dir.mkdir(parents=True, exist_ok=True)
        self._watcher = QFileSystemWatcher(self)
        self._watcher.addPath(str(plans_dir))
        self._watch_files()
        self._watcher.directoryChanged.connect(self._on_dir_changed)
        self._watcher.fileChanged.connect(self._on_file_changed)

    def _watch_files(self):
        plans_dir = system.manager.plans.PLANS_DIR
        watched = set(self._watcher.files())
        for p in plans_dir.glob('*.md'):
            s = str(p)
            if s not in watched:
                self._watcher.addPath(s)

    def _on_dir_changed(self, _path):
        self._sync_tree_with_disk()
        self.load()
        self._watch_files()

    def _on_file_changed(self, path):
        """A file changed on disk. If it's the one currently open in the
        editor, refresh the right pane — but only when the new content
        actually differs from what the editor is already showing (avoids
        clobbering the cursor after our own write).
        """
        item_id = self.get_selected_item_id()
        if item_id is None:
            return
        mgr = system.manager.plans
        name = self._name_for(item_id)
        if not name or str(mgr.path_for(name)) != path:
            return
        new_body = mgr.read(name)
        current = self.config_widget.get_config().get('data', '')
        if new_body == current:
            return
        self.config_widget.load_config({'data': new_body})
        self.config_widget.load()
        # Re-add: atomic-rename editors invalidate the watch on the old inode.
        if path not in self._watcher.files():
            self._watcher.addPath(path)

    class Plan_Config_Widget(ConfigJoined):
        """Right pane: the plan markdown editor stacked over a chat that
        drives a Claude Code agent to edit the plan file.

        The document body (``{'data': ...}``) is owned by the editor, so the
        page's existing on_item_selected/save_config and the disk watcher
        keep working unchanged. The chat is excluded from config aggregation
        (``propagate_config = False``) and driven separately via
        ``load_for_plan`` — it never writes the body itself, it edits the
        ``.md`` file on disk, which the watcher picks up.
        """
        def __init__(self, parent):
            self.propagate_config = True
            self.editor = self.Plan_Body_Editor(parent=self)
            self.chat = self.PlanChatWidget(parent=self)
            self.chat.propagate_config = False
            super().__init__(
                parent=parent,
                widgets=[self.editor, self.chat],
                layout_type='vertical',
                resizable=True,
                propagate_config=True,
            )

        def after_init(self):
            self.splitter.setSizes([700, 400])

        def maybe_rebuild_schema(self, schema_overrides, item_id):
            self.editor.maybe_rebuild_schema(schema_overrides, item_id)

        def load_config(self, json_config=None):
            # Only the editor takes the plan body; the chat loads its own
            # per-plan context via load_for_plan().
            self.editor.load_config(json_config)

        def load(self):
            self.editor.load()

        class Plan_Body_Editor(ConfigFields):
            def __init__(self, parent):
                super().__init__(parent=parent)
                self.schema = [
                    {
                        'text': '',
                        'key': 'data',
                        'type': str,
                        'num_lines': 20,
                        'stretch_x': True,
                        'stretch_y': True,
                        'label_position': None,
                        'wrap_text': True,
                        'default': '',
                    },
                ]

        class PlanChatWidget(ChattableWorkflowWidget):
            """Chat that edits the selected plan via a Claude Code agent.

            Unlike the Blocks/Tools chat (which *runs* the workflow), this
            hosts a fixed single Claude Code member whose working directory
            is the plans folder. As you chat, the agent reads and edits the
            plan's ``.md`` file directly; the Plans page's file watcher then
            refreshes the editor pane. Each plan keeps its own persistent
            conversation, stored as a context whose id is saved on the plan
            row.
            """

            def __init__(self, parent):
                super().__init__(parent=parent, kind='PLAN', show_workflow=False)
                self._plan_item_id = None

            def load_config(self, json_config=None):
                # Driven explicitly by load_for_plan(), not by the shared
                # config flow — avoid the default new_context() so no stray
                # empty contexts are created when a plan is selected.
                pass

            def load_for_plan(self, item_id, name):
                """Load (or create) this plan's conversation and target its file."""
                self._plan_item_id = item_id
                slug = system.manager.plans._slug(name)

                plan_cfg = sql.get_scalar(
                    "SELECT config FROM plans WHERE id = ?", (item_id,), load_json=True
                ) or {}
                context_id = plan_cfg.get('chat_context_id')

                if context_id and sql.get_scalar(
                    "SELECT 1 FROM contexts WHERE id = ?", (context_id,)
                ):
                    self.goto_context(context_id)
                    return

                config = self._build_plan_workflow_config(slug)
                sql.execute(
                    "INSERT INTO contexts (kind, config) VALUES (?, ?)",
                    (self.kind, json.dumps(config)),
                )
                context_id = sql.get_scalar(
                    "SELECT MAX(id) FROM contexts WHERE kind = ?", (self.kind,)
                )
                plan_cfg['chat_context_id'] = context_id
                sql.execute(
                    "UPDATE plans SET config = ? WHERE id = ?",
                    (json.dumps(plan_cfg), item_id),
                )
                self.goto_context(context_id)

            def _build_plan_workflow_config(self, slug):
                plans_dir = str(system.manager.plans.PLANS_DIR)
                sys_msg = (
                    "You are a planning assistant embedded in AgentPilot's "
                    "Plans page. The user is collaboratively editing a "
                    f"markdown plan stored at `{slug}.md` in your current "
                    "working directory.\n\n"
                    f"When the user asks for changes, read `{slug}.md` first, "
                    "then use the Edit/Write tools to update that same file "
                    "in place. Keep it clean, well-structured markdown. Do "
                    "not create other files or touch anything outside this "
                    "plan unless explicitly asked. Reply briefly in chat "
                    "describing what you changed."
                )
                return {
                    '_TYPE': 'workflow',
                    'name': 'Plan Assistant',
                    'members': [
                        {
                            'id': '1',
                            'linked_id': None,
                            'loc_x': 20,
                            'loc_y': 64,
                            'width': 450,
                            'height': 350,
                            'config': {'_TYPE': 'user', 'name': 'You'},
                        },
                        {
                            'id': '3',
                            'linked_id': None,
                            'loc_x': 112,
                            'loc_y': 66,
                            'width': 450,
                            'height': 350,
                            'config': {
                                '_TYPE': 'claude_code',
                                'name': 'Plan Editor',
                                'working_dir': plans_dir,
                                'chat.sys_msg': sys_msg,
                                'chat.permission_mode': 'default',
                                'builtin_tools': {
                                    'bash': False,
                                    'read': True,
                                    'write': True,
                                    'edit': True,
                                    'glob': True,
                                    'grep': True,
                                    'webfetch': False,
                                    'websearch': False,
                                },
                            },
                        },
                    ],
                    'inputs': [],
                    'options': {
                        'autorun': True,
                        'show_hidden_bubbles': False,
                        'show_nested_bubbles': False,
                        'mini_view': True,
                    },
                    'params': [],
                }
