import json
import os
import shutil

from PySide6.QtCore import Qt, QMimeData, QUrl
from PySide6.QtGui import QDrag, QIcon, QPixmap
from PySide6.QtWidgets import (
    QTreeWidget, QTreeWidgetItem, QMenu,
    QInputDialog, QMessageBox, QAbstractItemView
)

from gui.widgets.config_widget import ConfigWidget
from gui.util import CVBoxLayout, TreeButtons, colorize_pixmap
from utils import sql

from utils.helpers import ALL_MEDIA_EXTS, get_media_icon_path, get_media_type_from_ext

SETTINGS_KEY = 'video_studio_global_collections'


class CollectionsWidget(ConfigWidget):
    """Tree view widget for organizing media assets."""

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.root_path = 'collections/'
        self.default_folders = ['scenes', 'characters']
        self.folder_key = 'collections'  # Enable folder button in TreeButtons

        self.layout = CVBoxLayout(self)

        # Add tree buttons toolbar
        self.tree_buttons = TreeButtons(parent=self, extra_buttons=[
            {
                'text': 'Toggle Global',
                'icon_path': ':/resources/icon-globe.png',
                'target': self.toggle_global,
                'tooltip': 'Toggle selected folder as global',
            },
        ])
        self.layout.addWidget(self.tree_buttons)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setDragEnabled(True)
        self.tree.setDragDropMode(QAbstractItemView.DragOnly)
        self.tree.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self.show_context_menu)
        self.tree.itemDoubleClicked.connect(self.on_item_double_clicked)

        self.layout.addWidget(self.tree)

        self._ensure_root_path()
        self.load()

    def build_schema(self):
        """Override to prevent ConfigWidget from calling build_columns_from_schema on QTreeWidget."""
        pass

    def _ensure_root_path(self):
        """Ensure the collections root directory and default folders exist."""
        if not os.path.exists(self.root_path):
            os.makedirs(self.root_path)

        for folder in self.default_folders:
            folder_path = os.path.join(self.root_path, folder)
            if not os.path.exists(folder_path):
                os.makedirs(folder_path)

    def _get_global_collections(self):
        """Load global collections from settings table."""
        value = sql.get_scalar(
            f"SELECT value FROM settings WHERE field = ?",
            (SETTINGS_KEY,),
            load_json=True
        )
        return value if isinstance(value, dict) else {}

    def _save_global_collections(self, collections):
        """Save global collections to settings table."""
        existing = sql.get_scalar(
            f"SELECT value FROM settings WHERE field = ?",
            (SETTINGS_KEY,)
        )
        if existing is None:
            sql.execute(
                "INSERT INTO settings (field, value) VALUES (?, ?)",
                (SETTINGS_KEY, json.dumps(collections))
            )
        else:
            sql.execute(
                "UPDATE settings SET value = ? WHERE field = ?",
                (json.dumps(collections), SETTINGS_KEY)
            )

    def load(self):
        """Load the collections tree from filesystem and global storage."""
        self.tree.clear()

        # Load global collections first
        global_collections = self._get_global_collections()
        for folder_name, folder_data in global_collections.items():
            folder_item = QTreeWidgetItem([f"🌐 {folder_name}"])
            folder_item.setData(0, Qt.UserRole, folder_name)
            folder_item.setData(0, Qt.UserRole + 1, 'global_folder')
            folder_item.setData(0, Qt.UserRole + 2, folder_data)  # Store clips data
            folder_item.setIcon(0, QIcon(colorize_pixmap(QPixmap(':/resources/icon-folder.png'))))

            # Load items from global folder
            items = folder_data.get('items', [])
            for item_data in items:
                item_name = item_data.get('name', 'Untitled')
                file_item = QTreeWidgetItem([item_name])
                file_item.setData(0, Qt.UserRole, item_data)  # Store full clip config
                file_item.setData(0, Qt.UserRole + 1, 'global_item')
                file_item.setFlags(file_item.flags() | Qt.ItemIsDragEnabled)

                media_type = item_data.get('_TYPE', 'video')
                icon_path = get_media_icon_path(media_type=media_type)
                file_item.setIcon(0, QIcon(colorize_pixmap(QPixmap(icon_path))))
                folder_item.addChild(file_item)

            self.tree.addTopLevelItem(folder_item)
            folder_item.setExpanded(True)

        # Load local filesystem folders
        if os.path.exists(self.root_path):
            for folder_name in sorted(os.listdir(self.root_path)):
                folder_path = os.path.join(self.root_path, folder_name)
                if not os.path.isdir(folder_path):
                    continue

                folder_item = QTreeWidgetItem([folder_name])
                folder_item.setData(0, Qt.UserRole, folder_path)
                folder_item.setData(0, Qt.UserRole + 1, 'folder')
                folder_item.setIcon(0, QIcon(colorize_pixmap(QPixmap(':/resources/icon-folder.png'))))
                folder_item.setFlags(folder_item.flags() | Qt.ItemIsDropEnabled)

                self._load_folder_contents(folder_item, folder_path)
                self.tree.addTopLevelItem(folder_item)
                folder_item.setExpanded(True)

    def _load_folder_contents(self, parent_item, folder_path):
        """Recursively load folder contents from filesystem."""
        if not os.path.exists(folder_path):
            return

        for filename in sorted(os.listdir(folder_path)):
            filepath = os.path.join(folder_path, filename)

            if os.path.isdir(filepath):
                subfolder_item = QTreeWidgetItem([filename])
                subfolder_item.setData(0, Qt.UserRole, filepath)
                subfolder_item.setData(0, Qt.UserRole + 1, 'folder')
                subfolder_item.setIcon(0, QIcon(colorize_pixmap(QPixmap(':/resources/icon-folder.png'))))
                self._load_folder_contents(subfolder_item, filepath)
                parent_item.addChild(subfolder_item)
            else:
                ext = os.path.splitext(filename)[1].lower()
                if ext not in ALL_MEDIA_EXTS:
                    continue

                file_item = QTreeWidgetItem([filename])
                file_item.setData(0, Qt.UserRole, filepath)
                file_item.setData(0, Qt.UserRole + 1, 'file')
                file_item.setFlags(file_item.flags() | Qt.ItemIsDragEnabled)

                icon_path = get_media_icon_path(ext=ext)
                file_item.setIcon(0, QIcon(colorize_pixmap(QPixmap(icon_path))))

                parent_item.addChild(file_item)

    def get_folders(self):
        """Return list of all folder names in collections."""
        folders = []
        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            item_type = item.data(0, Qt.UserRole + 1)
            if item_type in ('folder', 'global_folder'):
                # Strip globe emoji for global folders
                name = item.text(0)
                if name.startswith('🌐 '):
                    name = name[2:].strip()
                folders.append(name)
        return folders

    def add_item(self, folder_name=None, source_filepath=None, clip_config=None):
        """Add a file or clip config to a collection folder.

        For local folders: copies the file to the folder.
        For global folders: stores the serialized clip config.
        """
        # If called from TreeButtons without args, prompt user
        if folder_name is None:
            item = self.tree.currentItem()
            if item:
                item_type = item.data(0, Qt.UserRole + 1)
                if item_type == 'global_folder':
                    QMessageBox.information(
                        self, "Add Item",
                        "To add items to a global folder, select a clip on the timeline "
                        "and use 'Add to Collection' from the context menu."
                    )
                    return
                elif item_type == 'folder':
                    # For local folders, open file dialog
                    from PySide6.QtWidgets import QFileDialog
                    filters = [
                        "Media Files (*.mp4 *.avi *.mov *.mkv *.webm *.png *.jpg *.jpeg *.gif *.mp3 *.wav *.flac)",
                        "All Files (*)"
                    ]
                    filepath, _ = QFileDialog.getOpenFileName(
                        self, "Add Media File", "", ";;".join(filters)
                    )
                    if filepath:
                        folder_path = item.data(0, Qt.UserRole)
                        folder_name = os.path.basename(folder_path)
                        return self.add_item(folder_name, source_filepath=filepath)
            return

        # Find if this is a global or local folder
        is_global = False
        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            item_type = item.data(0, Qt.UserRole + 1)
            name = item.text(0)
            if name.startswith('🌐 '):
                name = name[2:].strip()
            if name == folder_name and item_type == 'global_folder':
                is_global = True
                break

        if is_global:
            # Add to global collection (store clip config)
            if clip_config is None:
                return False
            global_collections = self._get_global_collections()
            if folder_name not in global_collections:
                global_collections[folder_name] = {'items': []}
            global_collections[folder_name]['items'].append(clip_config)
            self._save_global_collections(global_collections)
            self.load()
            return True
        else:
            # Add to local collection (copy file)
            if source_filepath is None or not os.path.exists(source_filepath):
                return False

            dest_folder = os.path.join(self.root_path, folder_name)
            if not os.path.exists(dest_folder):
                os.makedirs(dest_folder)

            filename = os.path.basename(source_filepath)
            dest_filepath = os.path.join(dest_folder, filename)

            # Handle duplicate filenames
            if os.path.exists(dest_filepath):
                base, ext = os.path.splitext(filename)
                counter = 1
                while os.path.exists(dest_filepath):
                    dest_filepath = os.path.join(dest_folder, f"{base}_{counter}{ext}")
                    counter += 1

            shutil.copy2(source_filepath, dest_filepath)
            self.load()
            return True

    def delete_item(self):
        """Delete the currently selected item."""
        item = self.tree.currentItem()
        if item is None:
            return

        item_type = item.data(0, Qt.UserRole + 1)

        if item_type == 'global_folder':
            self.delete_global_folder(item)
        elif item_type == 'global_item':
            self.delete_global_item(item)
        elif item_type == 'folder':
            self.delete_folder(item)
        elif item_type == 'file':
            self.delete_file(item)

    def add_folder(self, parent_item=None):
        """Add a new folder to collections."""
        name, ok = QInputDialog.getText(self, "New Folder", "Enter folder name:")
        if not ok or not name:
            return

        if parent_item and parent_item.data(0, Qt.UserRole + 1) == 'global_folder':
            QMessageBox.warning(self, "Error", "Cannot create subfolders in global folders.")
            return

        if parent_item:
            parent_path = parent_item.data(0, Qt.UserRole)
        else:
            parent_path = self.root_path

        new_folder_path = os.path.join(parent_path, name)

        if os.path.exists(new_folder_path):
            QMessageBox.warning(self, "Error", "A folder with that name already exists.")
            return

        os.makedirs(new_folder_path)
        self.load()

    def toggle_global(self):
        """Toggle the selected folder between local and global."""
        item = self.tree.currentItem()
        if item is None:
            QMessageBox.information(self, "Toggle Global", "Please select a folder first.")
            return

        item_type = item.data(0, Qt.UserRole + 1)

        if item_type == 'folder':
            # Convert local folder to global
            folder_path = item.data(0, Qt.UserRole)
            folder_name = item.text(0)

            reply = QMessageBox.question(
                self, "Make Global",
                f"Convert '{folder_name}' to a global folder?\n\n"
                "Global folders are accessible across all projects.\n"
                "The local files will be removed and clips will be stored as configs.",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply != QMessageBox.Yes:
                return

            # Collect file configs from local folder
            items = []
            for j in range(item.childCount()):
                child = item.child(j)
                if child.data(0, Qt.UserRole + 1) == 'file':
                    filepath = child.data(0, Qt.UserRole)
                    ext = os.path.splitext(filepath)[1].lower()
                    media_type = get_media_type_from_ext(ext)

                    items.append({
                        '_TYPE': media_type,
                        'name': os.path.basename(filepath),
                        'browse': {'path': filepath},
                    })

            # Save as global
            global_collections = self._get_global_collections()
            global_collections[folder_name] = {'items': items}
            self._save_global_collections(global_collections)

            # Remove local folder
            shutil.rmtree(folder_path)
            self.load()

        elif item_type == 'global_folder':
            # Convert global folder to local
            folder_name = item.data(0, Qt.UserRole)

            reply = QMessageBox.question(
                self, "Make Local",
                f"Convert '{folder_name}' to a local folder?\n\n"
                "The folder will no longer be accessible across projects.\n"
                "Only items with valid file paths will be preserved.",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply != QMessageBox.Yes:
                return

            folder_data = item.data(0, Qt.UserRole + 2)
            items = folder_data.get('items', [])

            # Create local folder
            folder_path = os.path.join(self.root_path, folder_name)
            os.makedirs(folder_path, exist_ok=True)

            # Copy files that have valid paths
            for item_config in items:
                browse = item_config.get('browse', {})
                filepath = browse.get('path', '')
                if filepath and os.path.exists(filepath):
                    dest = os.path.join(folder_path, os.path.basename(filepath))
                    if not os.path.exists(dest):
                        shutil.copy2(filepath, dest)

            # Remove from global
            global_collections = self._get_global_collections()
            if folder_name in global_collections:
                del global_collections[folder_name]
            self._save_global_collections(global_collections)

            self.load()
        else:
            QMessageBox.information(self, "Toggle Global", "Please select a folder (not a file).")

    def delete_global_folder(self, item):
        """Delete a global folder."""
        folder_name = item.data(0, Qt.UserRole)

        reply = QMessageBox.question(
            self, "Delete Global Folder",
            f"Are you sure you want to delete the global folder '{folder_name}'?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        global_collections = self._get_global_collections()
        if folder_name in global_collections:
            del global_collections[folder_name]
        self._save_global_collections(global_collections)
        self.load()

    def delete_global_item(self, item):
        """Delete an item from a global folder."""
        parent = item.parent()
        if not parent:
            return

        folder_name = parent.data(0, Qt.UserRole)
        item_config = item.data(0, Qt.UserRole)
        item_name = item.text(0)

        reply = QMessageBox.question(
            self, "Remove from Collection",
            f"Remove '{item_name}' from the global collection?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        global_collections = self._get_global_collections()
        if folder_name in global_collections:
            items = global_collections[folder_name].get('items', [])
            # Remove matching item
            global_collections[folder_name]['items'] = [
                i for i in items if i != item_config
            ]
        self._save_global_collections(global_collections)
        self.load()

    def delete_folder(self, item):
        """Delete a local folder and its contents."""
        folder_path = item.data(0, Qt.UserRole)
        folder_name = item.text(0)

        reply = QMessageBox.question(
            self, "Delete Folder",
            f"Are you sure you want to delete '{folder_name}' and all its contents?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        shutil.rmtree(folder_path)
        self.load()

    def delete_file(self, item):
        """Delete a file from local collections."""
        filepath = item.data(0, Qt.UserRole)
        filename = item.text(0)

        reply = QMessageBox.question(
            self, "Remove from Collection",
            f"Remove '{filename}' from the collection?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        os.remove(filepath)
        self.load()

    def show_context_menu(self, position):
        """Show context menu for tree items."""
        item = self.tree.itemAt(position)
        menu = QMenu(self)

        if item is None:
            add_folder_action = menu.addAction("New Folder")
            add_folder_action.triggered.connect(lambda: self.add_folder())
            add_global_action = menu.addAction("New Global Folder")
            add_global_action.triggered.connect(self.add_global_folder)
        else:
            item_type = item.data(0, Qt.UserRole + 1)

            if item_type == 'folder':
                add_subfolder_action = menu.addAction("New Subfolder")
                add_subfolder_action.triggered.connect(lambda: self.add_folder(item))
                menu.addSeparator()

                toggle_global_action = menu.addAction("Make Global")
                toggle_global_action.triggered.connect(self.toggle_global)
                menu.addSeparator()

                rename_action = menu.addAction("Rename")
                rename_action.triggered.connect(lambda: self.rename_item(item))

                delete_action = menu.addAction("Delete Folder")
                delete_action.triggered.connect(lambda: self.delete_folder(item))

            elif item_type == 'global_folder':
                toggle_local_action = menu.addAction("Make Local")
                toggle_local_action.triggered.connect(self.toggle_global)
                menu.addSeparator()

                delete_action = menu.addAction("Delete Folder")
                delete_action.triggered.connect(lambda: self.delete_global_folder(item))

            elif item_type == 'file':
                rename_action = menu.addAction("Rename")
                rename_action.triggered.connect(lambda: self.rename_item(item))

                delete_action = menu.addAction("Remove from Collection")
                delete_action.triggered.connect(lambda: self.delete_file(item))

            elif item_type == 'global_item':
                delete_action = menu.addAction("Remove from Collection")
                delete_action.triggered.connect(lambda: self.delete_global_item(item))

        menu.exec_(self.tree.mapToGlobal(position))

    def add_global_folder(self):
        """Add a new global folder."""
        name, ok = QInputDialog.getText(self, "New Global Folder", "Enter folder name:")
        if not ok or not name:
            return

        global_collections = self._get_global_collections()
        if name in global_collections:
            QMessageBox.warning(self, "Error", "A global folder with that name already exists.")
            return

        global_collections[name] = {'items': []}
        self._save_global_collections(global_collections)
        self.load()

    def rename_item(self, item):
        """Rename a folder or file."""
        item_type = item.data(0, Qt.UserRole + 1)

        if item_type in ('global_folder', 'global_item'):
            QMessageBox.information(self, "Rename", "Renaming global items is not yet supported.")
            return

        old_path = item.data(0, Qt.UserRole)
        old_name = item.text(0)

        label = "Enter new name:" if item_type == 'folder' else "Enter new filename:"
        new_name, ok = QInputDialog.getText(self, "Rename", label, text=old_name)

        if not ok or not new_name or new_name == old_name:
            return

        parent_path = os.path.dirname(old_path)
        new_path = os.path.join(parent_path, new_name)

        if os.path.exists(new_path):
            QMessageBox.warning(self, "Error", "An item with that name already exists.")
            return

        os.rename(old_path, new_path)
        self.load()

    def on_item_double_clicked(self, item, column):
        """Handle double-click to expand/collapse folders."""
        item_type = item.data(0, Qt.UserRole + 1)
        if item_type in ('folder', 'global_folder'):
            item.setExpanded(not item.isExpanded())

    def startDrag(self, supportedActions):
        """Start drag operation for tree items."""
        item = self.tree.currentItem()
        if not item:
            return

        item_type = item.data(0, Qt.UserRole + 1)

        if item_type == 'file':
            filepath = item.data(0, Qt.UserRole)
            if not filepath or not os.path.exists(filepath):
                return

            mime_data = QMimeData()
            mime_data.setUrls([QUrl.fromLocalFile(filepath)])

            drag = QDrag(self.tree)
            drag.setMimeData(mime_data)
            drag.exec_(Qt.CopyAction)

        elif item_type == 'global_item':
            # For global items, we pass the config as JSON in mime data
            item_config = item.data(0, Qt.UserRole)
            filepath = item_config.get('browse', {}).get('path', '')

            if filepath and os.path.exists(filepath):
                mime_data = QMimeData()
                mime_data.setUrls([QUrl.fromLocalFile(filepath)])
                drag = QDrag(self.tree)
                drag.setMimeData(mime_data)
                drag.exec_(Qt.CopyAction)

    def mouseMoveEvent(self, event):
        """Handle mouse move for drag initiation."""
        if event.buttons() == Qt.LeftButton:
            item = self.tree.currentItem()
            if item:
                item_type = item.data(0, Qt.UserRole + 1)
                if item_type in ('file', 'global_item'):
                    self.startDrag(Qt.CopyAction)
        super().mouseMoveEvent(event)

    def is_folder_global(self, folder_name):
        """Check if a folder is global."""
        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            item_type = item.data(0, Qt.UserRole + 1)
            name = item.text(0)
            if name.startswith('🌐 '):
                name = name[2:].strip()
            if name == folder_name:
                return item_type == 'global_folder'
        return False