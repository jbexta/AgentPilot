import json
from functools import partial
from PySide6.QtWidgets import QMenu, QWidgetAction, QWidget, QHBoxLayout, QLabel, QMessageBox

from utils import sql
from utils.helpers import display_message_box, display_message, get_text
from gui.gui_utils.icon_button import IconButton


class PresetMenu(IconButton):
    def __init__(self, parent, **kwargs):
        super().__init__(
            parent=parent,
            icon_path=':/resources/icon-save.png',
            size=24,
        )
        self.setToolTip('Presets')
        self.is_member_header = getattr(parent, 'is_member_header', True)

        self.menu = QMenu(self)

        self.clicked.connect(self.show_menu)

    def show_menu(self):
        self.menu.clear()
        self.build_menu(self.menu)

        button_rect = self.rect()
        menu_pos = self.mapToGlobal(button_rect.bottomLeft())
        self.menu.exec(menu_pos)

    def build_menu(self, menu):
        """Populate the given menu with preset actions."""
        menu.addAction('Save as preset', self.save_as_preset)
        menu.addSeparator()

        presets = sql.get_results("""
            SELECT name, config
            FROM entities
            WHERE kind = 'PRESET'
            ORDER BY name COLLATE NOCASE
        """)
        for name, config_json in presets:
            self.add_preset_action(menu, name, config_json)

    @staticmethod
    def _close_menu_chain(menu):
        while isinstance(menu, QMenu):
            menu.close()
            menu = menu.parent()

    def add_preset_action(self, menu, name, config_json):
        row = QWidget(menu)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(8, 2, 4, 2)
        layout.setSpacing(6)

        label = QLabel(name, parent=row)
        layout.addWidget(label, 1)

        delete_btn = IconButton(
            parent=row,
            icon_path=':/resources/icon-delete.png',
            size=18,
            tooltip='Delete preset',
        )
        delete_btn.clicked.connect(partial(self.delete_preset, menu, name))
        layout.addWidget(delete_btn)

        def apply_and_close(event):
            self._close_menu_chain(menu)
            self.apply_preset(config_json)
        row.mouseReleaseEvent = apply_and_close

        widget_action = QWidgetAction(menu)
        widget_action.setDefaultWidget(row)
        menu.addAction(widget_action)

    def delete_preset(self, menu, name):
        self._close_menu_chain(menu)
        retval = display_message_box(
            icon=QMessageBox.Warning,
            title='Delete preset',
            text=f"Are you sure you want to delete the preset '{name}'?",
            buttons=QMessageBox.Yes | QMessageBox.No,
        )
        if retval != QMessageBox.Yes:
            return
        sql.execute("DELETE FROM entities WHERE name = ? AND kind = 'PRESET'", (name,))

    def _resolve_context(self):
        """Resolve the host widget the header lives in.
        Returns (kind, host) where kind is one of
        'member_header', 'studio', 'proxy', 'workflow_header'."""
        host = self.parent.parent.parent
        if host.__class__.__name__ == 'MemberProxy':
            return 'proxy', host
        if self.is_member_header:
            # Both the workflow and video studio member panels are class-named
            # 'MemberConfigWidget'; the studio's parent has a timeline instead
            # of members_in_view.
            if hasattr(host.parent, 'timeline'):
                return 'studio', host
            return 'member_header', host
        return 'workflow_header', host

    def _get_workflow_target(self, workflow_settings):
        """Resolve the single target member of a simplified workflow header."""
        members = sorted(workflow_settings.members_in_view.values(), key=lambda m: m.x())
        user_members = [m for m in members if m.member_config.get('_TYPE', 'agent') == 'user']
        non_user_members = [m for m in members if m.member_config.get('_TYPE', 'agent') != 'user']
        if len(non_user_members) > 1:
            return None
        elif len(non_user_members) == 1:
            return non_user_members[0]
        elif len(user_members) > 0:
            return user_members[-1]
        return None

    def save_as_preset(self):
        kind, host = self._resolve_context()
        if kind in ('member_header', 'studio'):
            config = host.get_config()
        elif kind == 'proxy':
            config = dict(host.parent.member_config)
        else:
            target = self._get_workflow_target(host)
            if target is None:
                return
            config = dict(target.member_config)
        if not config:
            return

        new_name, ok = get_text(self, 'New Preset', 'Enter a name for the preset:')
        if not ok or not new_name:
            return

        config = {k: v for k, v in config.items() if not k.startswith('preview.')}
        config_json = json.dumps(config)
        existing_kind = sql.get_scalar("SELECT kind FROM entities WHERE name = ?", (new_name,))
        if existing_kind == 'PRESET':
            sql.execute("""
                UPDATE entities SET config = ?
                WHERE name = ? AND kind = 'PRESET'
            """, (config_json, new_name,))
        elif existing_kind is not None:
            display_message(
                message='This name is already in use.',
                icon='Warning',
            )
        else:
            sql.execute("""
                INSERT INTO entities (name, kind, config)
                VALUES (?, 'PRESET', ?)
            """, (new_name, config_json,))

    def apply_preset(self, config_json):
        preset_config = json.loads(config_json)
        kind, host = self._resolve_context()

        if kind == 'studio':
            studio = host.parent
            member_id = getattr(host.config_widget, 'member_id', None)
            clip = studio.timeline.clips.get(member_id)
            if clip is None:
                return
            clip_config = clip.member_config
            preset_config['_TYPE'] = clip.member_type
            # Keep the clip's own media source and preview state
            preset_config['browse.path'] = clip_config.get('browse.path', '')
            preset_config = {k: v for k, v in preset_config.items() if not k.startswith('preview.')}
            preset_config.update({k: v for k, v in clip_config.items() if k.startswith('preview.')})
            clip.member_config = preset_config
            host.display_member(member=clip)
            studio.update_config()
            return

        if kind == 'member_header':
            workflow_settings = host.parent
            member_id = getattr(host.config_widget, 'member_id', None)
            if member_id is None or member_id not in workflow_settings.members_in_view:
                return
            member = workflow_settings.members_in_view[member_id]
            member.member_config.clear()
            member.member_config.update(preset_config)
        elif kind == 'proxy':
            draggable_member = host.parent
            workflow_settings = host.workflow_settings
            draggable_member.member_config.clear()
            draggable_member.member_config.update(preset_config)
        else:
            workflow_settings = host
            target = self._get_workflow_target(workflow_settings)
            if target is None:
                return
            target.member_config.clear()
            target.member_config.update(preset_config)

        workflow_settings.update_config()
        workflow_settings.load()
