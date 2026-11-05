import importlib
import os
import sys
from pathlib import Path

import qasync
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QTreeWidgetItem, QMessageBox

from gui import system
from gui.gui_utils.helpers import safe_single_shot
from gui.gui_utils.custom_menu import CustomMenu
from gui.widgets.config_tree import ConfigTree
from utils.filesystem import get_application_path
from utils.helpers import block_signals, display_message, set_module_type

STATUS_COLORS = {
    'Running': '#6aab73',
    'Stopped': '#c9c9c9',
    'Disabled': '#B94343',
    'Not loaded': '#d2a15a',
}


@set_module_type(module_type='Pages')
class Page_Daemons_Settings(ConfigTree):
    """Start, stop and enable/disable the daemon modules found on disk.

    Unlike most trees this one isn't backed by the database — a daemon that
    has been disabled is invisible to ``ModulesController`` (its file name is
    underscore-prefixed, so ``discover_modules`` skips it), so the rows are
    scanned straight off the filesystem and cross-referenced with
    ``DaemonManager`` for live state.
    """
    display_name = 'Daemons'
    icon_path = ':/resources/icon-run.png'
    page_type = 'settings'  # either 'settings', 'main', or 'any' ('any' means it can be pinned between main and settings)

    def __init__(self, parent):
        super().__init__(
            parent=parent,
            schema=[
                {
                    'text': 'Daemon',
                    'key': 'name',
                    'type': str,
                    'stretch': True,
                },
                {
                    'text': 'Source',
                    'key': 'source',
                    'type': str,
                    'width': 140,
                },
                {
                    'text': 'Status',
                    'key': 'status',
                    'type': str,
                    'width': 100,
                },
            ],
            show_tree_buttons=False,
            readonly=True,
        )
        self.propagate_config = False

        self.tree_buttons = self.DaemonButtons(parent=self)
        self.tree_layout.insertWidget(0, self.tree_buttons)

        self.refresh_timer = QTimer(self)
        self.refresh_timer.setInterval(2000)
        self.refresh_timer.timeout.connect(self.refresh_statuses)
        self.refresh_timer.start()

    class DaemonButtons(CustomMenu):
        def __init__(self, parent):
            super().__init__(parent)
            self.schema = [
                {
                    'text': 'Start',
                    'icon_path': ':/resources/icon-run.png',
                    'target': parent.start_daemon,
                    'enabled': lambda: parent.selected_status() == 'Stopped',
                },
                {
                    'text': 'Stop',
                    'icon_path': ':/resources/icon-stop.png',
                    'target': parent.stop_daemon,
                    'enabled': lambda: parent.selected_status() == 'Running',
                },
                {
                    'text': 'Restart',
                    'icon_path': ':/resources/icon-refresh.png',
                    'target': parent.restart_daemon,
                    'enabled': lambda: parent.selected_status() == 'Running',
                },
                {
                    'text': 'Disable',
                    'icon_path': ':/resources/icon-cross.png',
                    'tooltip': 'Disable the daemon by prefixing its file name with an underscore',
                    'target': parent.toggle_enabled,
                    'visibility_predicate': lambda: parent.selected_status() != 'Disabled',
                    'enabled': lambda: parent.can_toggle_enabled(),
                },
                {
                    'text': 'Enable',
                    'icon_path': ':/resources/icon-tick.svg',
                    'tooltip': 'Enable the daemon by removing the underscore from its file name',
                    'target': parent.toggle_enabled,
                    'visibility_predicate': lambda: parent.selected_status() == 'Disabled',
                    'enabled': lambda: parent.can_toggle_enabled(),
                },
            ]
            self.create_toolbar(parent)

    # region Loading

    def load(self):
        selected_name = self.selected_row().get('name') if self.selected_row() else None
        with block_signals(self.tree):
            self.tree.clear()
            for row in scan_daemons():
                item = QTreeWidgetItem(self.tree, [row['name'], row['source'], row['status']])
                item.setData(0, Qt.UserRole, row)
                item.setForeground(2, QColor(STATUS_COLORS.get(row['status'], '#c9c9c9')))
                if row['name'] == selected_name:
                    self.tree.setCurrentItem(item)

        self.tree_buttons.reload_predicates()

    def refresh_statuses(self):
        """Cheap tick that only re-derives live state, leaving the rows alone."""
        if not self.isVisible():
            return

        changed = False
        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            row = item.data(0, Qt.UserRole) or {}
            status = daemon_status(row.get('name'), row.get('enabled', False))
            if status == row.get('status'):
                continue
            row['status'] = status
            item.setData(0, Qt.UserRole, row)
            item.setText(2, status)
            item.setForeground(2, QColor(STATUS_COLORS.get(status, '#c9c9c9')))
            changed = True

        if changed:
            self.tree_buttons.reload_predicates()

    def on_item_selected(self):
        self.tree_buttons.reload_predicates()

    # endregion

    # region Actions

    def selected_row(self):
        item = self.tree.currentItem()
        if item is None:
            return None
        return item.data(0, Qt.UserRole)

    def selected_status(self):
        row = self.selected_row()
        return row.get('status') if row else None

    def can_toggle_enabled(self):
        if getattr(sys, 'frozen', False):
            return False  # disabling renames the source file, which a frozen build has none of
        return self.selected_row() is not None

    def start_daemon(self):
        row = self.selected_row()
        if not row:
            return
        if not system.manager.daemons.start_daemon(row['name']):
            display_message(f"Couldn't start daemon `{row['name']}`", 'Daemons', QMessageBox.Warning)
        safe_single_shot(100, self.refresh_statuses)

    def stop_daemon(self):
        row = self.selected_row()
        if not row:
            return
        system.manager.daemons.stop_daemon(row['name'])
        safe_single_shot(100, self.refresh_statuses)

    @qasync.asyncSlot()
    async def restart_daemon(self):
        row = self.selected_row()
        if not row:
            return
        if not await system.manager.daemons.restart_daemon(row['name']):
            display_message(f"Couldn't restart daemon `{row['name']}`", 'Daemons', QMessageBox.Warning)
        safe_single_shot(100, self.refresh_statuses)

    def toggle_enabled(self):
        row = self.selected_row()
        if not row:
            return
        if getattr(sys, 'frozen', False):
            display_message(
                'Daemons can only be enabled or disabled when running from source.',
                'Daemons', QMessageBox.Warning,
            )
            return

        path = Path(row['path'])
        if row['enabled']:
            system.manager.daemons.stop_daemon(row['name'])
            new_path = path.with_name(f'_{path.name}')
        else:
            new_path = path.with_name(path.name.lstrip('_'))

        if new_path.exists():
            display_message(f'`{new_path.name}` already exists', 'Daemons', QMessageBox.Warning)
            return

        try:
            path.rename(new_path)
        except OSError as e:
            display_message(f'Error renaming `{path.name}`: {e}', 'Daemons', QMessageBox.Warning)
            return

        # Drop the cached import of the old file name so a later re-enable
        # picks the source back up off disk rather than out of ``sys.modules``.
        sys.modules.pop(row['dotted_path'], None)
        reload_daemons()
        self.load()

    # endregion


def reload_daemons():
    """Re-discover daemon modules after a file has been renamed on disk."""
    importlib.invalidate_caches()

    controller = system.manager.modules.type_controllers.get('daemons')
    if controller is not None:
        # ``ModulesController.load`` upserts but never evicts, so a daemon
        # that was just disabled would otherwise linger in the controller.
        controller.clear()
        controller.load()

    system.manager.load_manager('daemons')


def daemon_status(daemon_name, enabled):
    if not enabled:
        return 'Disabled'
    daemons = system.manager.daemons
    if daemon_name in daemons.running_daemons:
        return 'Running'
    if daemon_name in daemons.available_daemons:
        return 'Stopped'
    return 'Not loaded'


def daemon_dirs():
    """Yield ``(fs_path, dotted_path, source_label)`` for every daemons folder.

    Mirrors ``ModulesController.get_plugin_module_dirs`` so the page shows
    exactly the folders module discovery would look in.
    """
    app_path = Path(get_application_path())

    core_dir = app_path / 'src' / 'core' / 'daemons'
    if core_dir.is_dir():
        yield core_dir, 'core.daemons', 'core'

    plugins_dir = app_path / 'src' / 'plugins'
    if not plugins_dir.is_dir():
        return

    for plugin_name in sorted(os.listdir(plugins_dir)):
        plugin_path = plugins_dir / plugin_name
        if not plugin_path.is_dir() or plugin_name.startswith('_'):
            continue

        base_dir = plugin_path / 'daemons'
        nested_dir = plugin_path / 'core' / 'daemons'
        if base_dir.is_dir():
            yield base_dir, f'plugins.{plugin_name}.daemons', plugin_name
        elif nested_dir.is_dir():
            yield nested_dir, f'plugins.{plugin_name}.core.daemons', plugin_name


def scan_daemons():
    """Scan the daemon folders on disk, including disabled (``_`` prefixed) files."""
    rows = []
    for fs_dir, dotted_dir, source in daemon_dirs():
        for file_name in sorted(os.listdir(fs_dir)):
            if not file_name.endswith('.py'):
                continue
            stem = file_name[:-3]
            if stem in ('__init__', 'base'):
                continue

            enabled = not stem.startswith('_')
            name = stem.lstrip('_')
            rows.append({
                'name': name,
                'source': source,
                'enabled': enabled,
                'path': str(fs_dir / file_name),
                'dotted_path': f'{dotted_dir}.{stem}',
                'status': daemon_status(name, enabled),
            })

    rows.sort(key=lambda r: (r['source'] != 'core', r['source'], r['name']))
    return rows
