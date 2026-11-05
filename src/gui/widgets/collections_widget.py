import json
import os
from functools import partial

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QCursor, QDrag, QIcon, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QFileDialog, QMenu, QMessageBox,
    QTreeWidgetItem,
)

from gui.gui_utils.helpers import colorize_pixmap
from gui.gui_utils.base_tree_widget import BaseTreeWidget
from gui.gui_utils.media_icon_list_widget import MediaIconListWidget
from gui.widgets.config_db_tree import ConfigDBTree
from gui.widgets.config_side_tabs import CollapsibleSection
from utils import sql
from utils.filesystem import get_application_path
from utils.helpers import display_message, display_message_box, get_text
from utils.media import (
    ALL_MEDIA_EXTS, get_media_icon_path, get_media_type_from_ext,
)

SETTINGS_KEY = 'current_project_collection'
GEN_DIRS = ('videos', 'music', 'images')
MAX_RECENT_FILES = 100

MEDIA_FILE_FILTER = ';;'.join([
    'Media Files (' + ' '.join(f'*{e}' for e in sorted(ALL_MEDIA_EXTS)) + ')',
    'All Files (*)',
])


class MediaTreeWidget(BaseTreeWidget):
    """BaseTreeWidget that drags media items out as file URLs (for media
    upload fields and the timeline) and imports dropped file URLs (from the
    recent generations list or a file manager) into the collection."""

    def __init__(self, parent, view_mode='list'):
        super().__init__(parent)
        self.view_mode = view_mode
        self._icon_grids = []
        self.setDragDropMode(QAbstractItemView.DragDrop)

    def _item_filepath(self, item):
        if item.data(0, Qt.UserRole) == 'folder':
            return None
        return sql.get_scalar("""
            SELECT json_extract(config, '$.path')
            FROM project_collection_items
            WHERE id = ?""", (int(item.text(1)),))

    def mimeData(self, items):
        mime_data = super().mimeData(items)
        urls = [QUrl.fromLocalFile(path) for item in items
                if (path := self._item_filepath(item)) and os.path.isfile(path)]
        if urls:
            mime_data.setUrls(urls)
        return mime_data

    def startDrag(self, supported_actions):
        items = self.selectedItems()
        if not items:
            return
        drag = QDrag(self)
        drag.setMimeData(self.mimeData(items))
        # Copy as the default action so external drop targets never trigger
        # Qt's remove-on-move behaviour; internal drops persist to the db.
        drag.exec_(Qt.CopyAction | Qt.MoveAction, Qt.CopyAction)

    def _target_folder_id(self, pos):
        item = self.itemAt(pos)
        if item is not None and item.data(0, Qt.UserRole) != 'folder':
            item = item.parent()
        if item is not None and item.data(0, Qt.UserRole) == 'folder':
            return int(item.text(1))
        return None

    def apply_view_mode(self):
        """In 'icons' mode, hide media item rows and show each folder's items
        (and root items) as an embedded icon grid row instead."""
        self._icon_grids = []
        if self.view_mode != 'icons':
            return
        self.blockSignals(True)
        try:
            self._build_icon_grids()
        finally:
            self.blockSignals(False)

    def _build_icon_grids(self):
        containers = [self.invisibleRootItem()]
        stack = [self.invisibleRootItem()]
        while stack:
            node = stack.pop()
            for i in range(node.childCount()):
                child = node.child(i)
                if child.data(0, Qt.UserRole) == 'folder':
                    containers.append(child)
                    stack.append(child)
        for container in containers:
            media_items = [
                container.child(i) for i in range(container.childCount())
                if container.child(i).data(0, Qt.UserRole) != 'folder']
            if not media_items:
                continue
            entries = []
            for item in media_items:
                filepath = self._item_filepath(item)
                if filepath:
                    entries.append((int(item.text(1)), filepath))
                item.setHidden(True)
            if not entries:
                continue
            grid_item = QTreeWidgetItem(container)
            grid_item.setData(0, Qt.UserRole, 'icon_grid')
            grid_item.setFlags(Qt.ItemIsEnabled)
            grid_item.setFirstColumnSpanned(True)
            grid = MediaIconListWidget(parent=self)
            grid.load_files(
                [filepath for _, filepath in entries],
                ids=[item_id for item_id, _ in entries])
            grid.itemClicked.connect(partial(self._on_grid_item_clicked, grid))
            self._icon_grids.append(grid)
            self._fit_grid_height(grid)
            self.setItemWidget(grid_item, 0, grid)

    def _fit_grid_height(self, grid):
        cell = grid.iconSize().width() + grid.spacing() * 2 + 8
        cols = max(1, self.viewport().width() // cell)
        rows = (grid.count() + cols - 1) // cols
        grid.setFixedHeight(rows * cell + 8)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        for grid in self._icon_grids:
            self._fit_grid_height(grid)

    def _on_grid_item_clicked(self, grid, item):
        for other in self._icon_grids:
            if other is not grid:
                other.clearSelection()
        hidden_item = self.items_mapping.get(item.data(Qt.UserRole + 1))
        if hidden_item is not None:
            self.setCurrentItem(hidden_item)

    def dragEnterEvent(self, event):
        if event.source() is self:
            super().dragEnterEvent(event)
        elif event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.source() is not self:
            event.acceptProposedAction()
            return
        super().dragMoveEvent(event)

    def dropEvent(self, event):
        source = event.source()
        item_ids = [item.data(Qt.UserRole + 1) for item in source.selectedItems()] \
            if isinstance(source, MediaIconListWidget) else []
        item_ids = [item_id for item_id in item_ids if item_id is not None]
        if item_ids:
            # Drag from an embedded icon grid: move within the collection
            folder_id = self._target_folder_id(event.pos())
            for item_id in item_ids:
                sql.execute("""
                    UPDATE project_collection_items
                    SET folder_id = ?, collection_id = ?
                    WHERE id = ?""",
                    (folder_id, self.parent.current_collection_id, item_id))
            event.acceptProposedAction()
            self.parent.load()
            return
        if source is not self:
            paths = [url.toLocalFile() for url in event.mimeData().urls()]
            self.parent.import_files(paths, self._target_folder_id(event.pos()))
            event.acceptProposedAction()
            return
        # Never drop a folder into itself or its own subtree (the embedded
        # grid rows are children, so this is easy to do by accident and
        # creates a parent_id cycle that hangs the folder loading loop)
        dragging_item = self.currentItem()
        node = self.itemAt(event.pos())
        while node is not None:
            if node is dragging_item:
                event.ignore()
                return
            node = node.parent()
        super().dropEvent(event)


class CollectionsWidget(ConfigDBTree):
    """Tree view widget for organizing media assets.

    Shows a 'Recent Generations' icon list on top, followed by the folders
    and media items of the active collection. The active collection is
    switched from a toolbar button."""

    def __init__(self, parent=None):
        self.current_collection_id = None
        self._ensure_collection()
        super().__init__(
            parent=parent,
            table_name='project_collection_items',
            tree_class=partial(MediaTreeWidget, view_mode='icons'),
            query="""
                SELECT
                    name,
                    id,
                    kind,
                    folder_id
                FROM project_collection_items
                WHERE collection_id = :collection_id
                ORDER BY pinned DESC, ordr, name COLLATE NOCASE""",
            query_params={'collection_id': lambda: self.current_collection_id},
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
                    'text': 'kind',
                    'key': 'kind',
                    'type': str,
                    'visible': False,
                },
            ],
            folder_key=f'collection:{self.current_collection_id}',
            del_item_options={'title': 'Remove Media', 'prompt': 'Remove this item from the collection?'},
            tree_header_hidden=True,
            init_select=False,
            searchable=True,
            extra_buttons=[
                {
                    'text': 'Collections',
                    'icon_path': ':/resources/icon-blocks.png',
                    'target': self.show_collections_menu,
                    'tooltip': 'Switch collection',
                },
            ],
        )
        self.recent_list = MediaIconListWidget(
            parent=self, on_delete=self.delete_recent_file)
        self.recent_list.setMaximumHeight(150)
        self.recent_section = CollapsibleSection(
            parent=self,
            title='Recent Generations',
            content_widget=self.recent_list,
        )
        self.tree_layout.addWidget(self.recent_section)

        self.build_schema()
        self.loaded_on_show = False

    def showEvent(self, event):
        super().showEvent(event)
        if not self.loaded_on_show:
            self.loaded_on_show = True
            self.load()

    def _ensure_collection(self):
        collection_ids = sql.get_results(
            "SELECT id FROM project_collections ORDER BY ordr, id",
            return_type='list')
        if not collection_ids:
            sql.execute("INSERT INTO project_collections (name) VALUES ('Default')")
            collection_ids = [sql.get_scalar("SELECT MAX(id) FROM project_collections")]

        last_id = sql.get_scalar(
            "SELECT value FROM settings WHERE field = ?", (SETTINGS_KEY,))
        if last_id is not None and int(last_id) in collection_ids:
            self.current_collection_id = int(last_id)
        else:
            self.current_collection_id = collection_ids[0]

    def _save_current_collection(self):
        existing = sql.get_scalar(
            "SELECT value FROM settings WHERE field = ?", (SETTINGS_KEY,))
        if existing is None:
            sql.execute("INSERT INTO settings (field, value) VALUES (?, ?)",
                        (SETTINGS_KEY, self.current_collection_id))
        else:
            sql.execute("UPDATE settings SET value = ? WHERE field = ?",
                        (self.current_collection_id, SETTINGS_KEY))

    def get_collections(self):
        """Return list of (id, name) for all collections."""
        return sql.get_results(
            "SELECT id, name FROM project_collections ORDER BY ordr, name COLLATE NOCASE")

    def set_collection(self, collection_id):
        self.current_collection_id = collection_id
        self.folder_key = f'collection:{collection_id}'
        self.manager.folder_key = self.folder_key
        self._save_current_collection()
        self.load()

    def show_collections_menu(self):
        menu = QMenu(self)
        for collection_id, name in self.get_collections():
            action = menu.addAction(name)
            action.setCheckable(True)
            action.setChecked(collection_id == self.current_collection_id)
            action.triggered.connect(partial(self.set_collection, collection_id))
        menu.addSeparator()
        menu.addAction('New Collection').triggered.connect(self.new_collection)
        menu.addAction('Rename Collection').triggered.connect(self.rename_collection)
        menu.addAction('Delete Collection').triggered.connect(self.delete_collection)
        menu.exec_(QCursor.pos())

    def new_collection(self):
        name, ok = get_text(self, 'New Collection', 'Enter a name for the collection:')
        if not ok or not name:
            return
        sql.execute("INSERT INTO project_collections (name) VALUES (?)", (name,))
        self.set_collection(sql.get_scalar("SELECT MAX(id) FROM project_collections"))

    def rename_collection(self):
        current_name = sql.get_scalar(
            "SELECT name FROM project_collections WHERE id = ?",
            (self.current_collection_id,))
        name, ok = get_text(self, 'Rename Collection', 'Enter a new name:', text=current_name)
        if not ok or not name:
            return
        sql.execute("UPDATE project_collections SET name = ? WHERE id = ?",
                    (name, self.current_collection_id))

    def delete_collection(self):
        retval = display_message_box(
            icon=QMessageBox.Warning,
            title='Delete Collection',
            text='Are you sure you want to delete this collection and all its items?',
            buttons=QMessageBox.Yes | QMessageBox.No,
        )
        if retval != QMessageBox.Yes:
            return
        sql.execute("DELETE FROM project_collection_items WHERE collection_id = ?",
                    (self.current_collection_id,))
        sql.execute("DELETE FROM folders WHERE type = ?",
                    (f'collection:{self.current_collection_id}',))
        sql.execute("DELETE FROM project_collections WHERE id = ?",
                    (self.current_collection_id,))
        self._ensure_collection()
        self.set_collection(self.current_collection_id)

    def load(self, *args, **kwargs):
        if self.current_collection_id is None:
            return
        super().load(*args, **kwargs)
        self._apply_media_icons()
        self.tree.apply_view_mode()
        if hasattr(self, 'recent_list'):
            self.recent_list.load_files(self._recent_generation_files())

    def _apply_media_icons(self):
        for item in self.tree.items_mapping.values():
            icon_path = get_media_icon_path(media_type=item.text(2))
            item.setIcon(0, QIcon(colorize_pixmap(QPixmap(icon_path))))

    def _recent_generation_files(self):
        """Return generated media files not yet in any collection, newest first."""
        known_paths = set(sql.get_results(
            "SELECT json_extract(config, '$.path') FROM project_collection_items",
            return_type='list'))
        files = []
        for subdir in GEN_DIRS:
            dir_path = os.path.join(get_application_path(), subdir)
            if not os.path.isdir(dir_path):
                continue
            for filename in os.listdir(dir_path):
                filepath = os.path.join(dir_path, filename)
                ext = os.path.splitext(filename)[1].lower()
                if ext in ALL_MEDIA_EXTS and os.path.isfile(filepath) \
                        and filepath not in known_paths:
                    files.append((os.path.getmtime(filepath), filepath))
        files.sort(reverse=True)
        return [filepath for _, filepath in files[:MAX_RECENT_FILES]]

    def delete_recent_file(self, filepath):
        retval = display_message_box(
            icon=QMessageBox.Warning,
            title='Delete Generation',
            text='Delete this generated file from disk?',
            buttons=QMessageBox.Yes | QMessageBox.No,
        )
        if retval != QMessageBox.Yes:
            return
        if filepath and os.path.isfile(filepath):
            os.remove(filepath)
        self.load()

    def add_media_item(self, filepath, folder_id=None, collection_id=None):
        """Insert a media file reference into a collection. Returns the new id."""
        kind = get_media_type_from_ext(os.path.splitext(filepath)[1].lower())
        if kind is None:
            display_message(
                message='Unsupported media file type',
                icon=QMessageBox.Warning,
            )
            return None
        sql.execute("""
            INSERT INTO project_collection_items (collection_id, name, kind, config, folder_id)
            VALUES (?, ?, ?, ?, ?)""",
            (collection_id or self.current_collection_id, os.path.basename(filepath),
             kind, json.dumps({'path': filepath}), folder_id))
        return sql.get_scalar("SELECT MAX(id) FROM project_collection_items")

    def import_files(self, filepaths, folder_id=None):
        """Add dropped files to the active collection."""
        item_id = None
        for filepath in filepaths:
            item_id = self.add_media_item(filepath, folder_id) or item_id
        if item_id:
            self.load(select_id=item_id)

    def add_item(self):
        filepath, _ = QFileDialog.getOpenFileName(
            self, 'Add Media File', '', MEDIA_FILE_FILTER)
        if not filepath:
            return
        item_id = self.add_media_item(filepath, self.tree.get_selected_folder_id())
        if item_id:
            self.load(select_id=item_id)
