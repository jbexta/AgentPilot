import json
import shutil

from PySide6.QtCore import Qt, QFileSystemWatcher
from PySide6.QtWidgets import QMessageBox

from gui import system
from gui.widgets.config_db_tree import ConfigDBTree
from gui.widgets.config_fields import ConfigFields
from plugins.workflows.utils.acp import agent_of
from plugins.workflows.utils.agent_kinds import AgentKindTree
from utils.helpers import display_message, get_text


class Page_Skill_Settings(AgentKindTree, ConfigDBTree):
    display_name = 'Skills'
    icon_path = ":/resources/icon-skills.png"
    page_type = 'any'  # either 'settings', 'main', or 'any'

    def __init__(self, parent):
        super().__init__(
            parent=parent,
            manager='skills',
            query="""
                SELECT name, id, uuid, folder_id, kind
                FROM skills
                ORDER BY kind, pinned DESC, ordr, name COLLATE NOCASE""",
            schema=[
                {'text': 'Name', 'key': 'name', 'type': str, 'stretch': True},
                {'text': 'id', 'key': 'id', 'type': int, 'visible': False},
                {'text': 'uuid', 'key': 'uuid', 'type': str, 'visible': False},
            ],
            readonly=False,
            layout_type='horizontal',
            tree_header_hidden=True,
            default_item_icon=':/resources/icon-block.png',
            config_widget=self.Skill_Config_Widget(parent=self),
            folder_key='skills',
            group_by_kind=True,
            searchable=True,
        )
        self.splitter.setSizes([400, 1000])

        self._sync_tree_with_disk()
        self._init_watcher()

    def on_edited(self):
        system.manager.skills.sync_to_disk()

    # File is the source of truth for description + body. The methods
    # below are shared with the project page's skills tree.

    def on_item_selected(self):
        item_id = self.get_selected_item_id()
        if not (item_id and self.config_widget):
            return ConfigDBTree.on_item_selected(self)
        self.toggle_config_widget(config_type='item')
        self.config_widget.maybe_rebuild_schema(self.schema_overrides, item_id)
        row = self._row_for(item_id)
        description, body = system.manager.skills.read(*row) if row else ('', '')
        self.config_widget.load_config({
            'description': description,
            'data': body,
            'app_only': self._db_config_for(item_id).get('app_only', False),
        })
        self.config_widget.load()

    def _db_config_for(self, item_id):
        raw = self.db_connector.get_scalar(
            "SELECT config FROM skills WHERE id = ?", (item_id,)
        )
        return json.loads(raw) if raw else {}

    def save_config(self):
        item_id = self.get_selected_item_id()
        if item_id is None:
            return
        row = self._row_for(item_id)
        if not row:
            return
        config = self.config_widget.get_config()
        mgr = system.manager.skills
        app_only = bool(config.get('app_only', False))
        db_config = self._db_config_for(item_id)
        if db_config.get('app_only', False) != app_only:
            db_config['app_only'] = app_only
            self.db_connector.execute(
                "UPDATE skills SET config = ? WHERE id = ?",
                (json.dumps(db_config), item_id)
            )
        mgr.write(
            *row,
            config.get('description', ''),
            config.get('data', ''),
        )
        mgr.sync_to_disk()

    def rename_item(self):
        item = self.tree.currentItem()
        if not item:
            return
        tag = item.data(0, Qt.UserRole)
        if tag == 'folder':
            return ConfigDBTree.rename_item(self)

        item_id = self.get_selected_item_id()
        if not item_id:
            return
        mgr = system.manager.skills
        row = self._row_for(item_id)
        if not row:
            return
        old_name, kind = row
        old_path = mgr.path_for(old_name, kind)
        old_dir = old_path.parent if old_path else None

        current = old_name
        while True:
            text, ok = get_text(
                self, 'Rename skill', 'Enter a new name for the skill:', text=current
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
            if new_slug == mgr._slug(old_name):
                return
            if mgr.exists(new_slug, kind, exclude_id=item_id):
                display_message(
                    message='A skill with that name already exists.',
                    icon=QMessageBox.Warning,
                )
                current = text
                continue
            new_dir = mgr.path_for(new_slug, kind).parent
            try:
                description, body = mgr.read(old_name, kind)
                if old_dir and old_dir.exists():
                    # Copy + delete instead of rename: on some filesystems
                    # (e.g. vboxsf) files inside a just-renamed directory
                    # transiently raise ENOENT, breaking the write below.
                    shutil.copytree(old_dir, new_dir)
                    shutil.rmtree(old_dir)
                self.db_connector.execute(
                    "UPDATE skills SET name = ? WHERE id = ?", (new_slug, item_id)
                )
                # Rewrite SKILL.md so the frontmatter `name:` matches the new slug.
                mgr.write(new_slug, kind, description, body)
                is_baked = self.db_connector.get_scalar(
                    "SELECT baked FROM skills WHERE id = ?", (item_id,)
                ) == 1
                if is_baked:
                    from gui.gui_utils.helpers import bake_table_item
                    bake_table_item('skills', item_id)
                mgr.sync_to_disk()
            except OSError as e:
                display_message(
                    message=f'Error renaming skill: {e}', icon=QMessageBox.Warning
                )
                return
            if hasattr(self, '_watch_skill_dirs'):
                self._watch_skill_dirs()
            self.load()
            return

    # -- tree ↔ disk identity sync ---------------------------------------------

    def _sync_tree_with_disk(self):
        mgr = system.manager.skills
        disk = set(mgr.list_files())
        rows = self.db_connector.get_results("SELECT id, name, kind FROM skills") or []
        db = {(agent_of(kind), mgr._slug(name)): row_id for row_id, name, kind in rows}
        for agent, slug in disk - db.keys():
            self.db_connector.execute(
                "INSERT INTO skills (name, kind) VALUES (?, ?)", (slug, agent)
            )
        for key in db.keys() - disk:
            self.db_connector.execute("DELETE FROM skills WHERE id = ?", (db[key],))

    # -- live watcher ----------------------------------------------------------

    def _init_watcher(self):
        mgr = system.manager.skills
        self._watcher = QFileSystemWatcher(self)
        self._watcher.addPath(str(mgr.ROOT))
        self._watch_skill_dirs()
        self._watch_external_roots()
        self._watcher.directoryChanged.connect(self._on_dir_changed)
        self._watcher.fileChanged.connect(self._on_file_changed)

    def _watch_external_roots(self):
        """Watch every agent's global and project skills dirs so skills
        dropped there by terminal sessions get adopted live."""
        watched = set(self._watcher.directories())
        for _, root in system.manager.skills.external_roots():
            if root.is_dir() and str(root) not in watched:
                self._watcher.addPath(str(root))

    def _watch_skill_dirs(self):
        """Watch each agent's ``skills/`` and ``<slug>/`` dir (for SKILL.md
        add/remove/rename) and each existing ``SKILL.md`` (for content
        changes)."""
        mgr = system.manager.skills
        watched = set(self._watcher.files()) | set(self._watcher.directories())
        for agent_dir in mgr.ROOT.iterdir():
            skills_dir = agent_dir / 'skills'
            if not skills_dir.is_dir():
                continue
            subs = [skills_dir] + [s for s in skills_dir.iterdir() if s.is_dir()]
            for sub in subs:
                if str(sub) not in watched:
                    self._watcher.addPath(str(sub))
                skill_md = sub / 'SKILL.md'
                if skill_md.exists() and str(skill_md) not in watched:
                    self._watcher.addPath(str(skill_md))

    def _on_dir_changed(self, _path):
        system.manager.skills.sync_to_disk()
        self._sync_tree_with_disk()
        self.load()
        self._watch_skill_dirs()
        self._watch_external_roots()

    def _on_file_changed(self, path):
        item_id = self.get_selected_item_id()
        if item_id is None:
            return
        mgr = system.manager.skills
        row = self._row_for(item_id)
        if not row or str(mgr.path_for(*row)) != path:
            return
        new_desc, new_body = mgr.read(*row)
        current_desc = self.config_widget.get_config().get('description', '')
        current_body = self.config_widget.get_config().get('data', '')
        if new_desc == current_desc and new_body == current_body:
            return
        self.config_widget.load_config({'description': new_desc, 'data': new_body})
        self.config_widget.load()
        if path not in self._watcher.files():
            self._watcher.addPath(path)

    class Skill_Config_Widget(ConfigFields):
        def __init__(self, parent):
            super().__init__(parent=parent)
            self.propagate_config = True
            self.schema = [
                {
                    'text': 'Description',
                    'key': 'description',
                    'type': str,
                    'num_lines': 2,
                    'stretch_x': True,
                    'wrap_text': True,
                    'default': '',
                    'label_position': 'top',
                },
                {
                    'text': 'Content',
                    'key': 'data',
                    'type': str,
                    'num_lines': 20,
                    'stretch_x': True,
                    'stretch_y': True,
                    'wrap_text': True,
                    'default': '',
                    'label_position': 'top',
                },
                {
                    'text': 'In-app only',
                    'key': 'app_only',
                    'type': bool,
                    'default': False,
                    'tooltip': 'Only visible to agent sessions running inside the app, never to terminal sessions',
                },
            ]
