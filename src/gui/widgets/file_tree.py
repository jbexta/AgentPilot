import os
import sys
import shutil
import stat
from datetime import datetime
from pathlib import Path
from typing import List
from functools import lru_cache

from PySide6.QtWidgets import *
from PySide6.QtCore import *
from PySide6.QtGui import *

from gui.util import clear_layout, IconButton, ToggleIconButton, CHBoxLayout, CVBoxLayout
from gui import system
from gui.widgets.config_joined import ConfigJoined
from gui.widgets.config_widget import ConfigWidget
from utils.helpers import display_message, display_message_box, set_module_type


class LazyFileSystemModel(QAbstractItemModel):
    """A lazy-loading file system model that loads items in batches for performance."""

    BATCH_SIZE = 200
    COLUMNS = ['Name', 'Size', 'Type', 'Date Modified']

    def __init__(self, parent=None):
        super().__init__(parent)
        self._root_path = None
        self._items = []  # List of DirEntry objects
        self._filtered_items = []  # Filtered view of items
        self._loaded_count = 0
        self._total_count = 0
        self._scandir_iter = None
        self._icon_provider = QFileIconProvider()
        self._name_filter = ''
        self._name_to_index = {}  # Cache for quick lookups
        self._sort_column = 0  # Default sort by name
        self._sort_order = Qt.AscendingOrder

    def setRootPath(self, path: str):
        """Set the root directory to display."""
        self.beginResetModel()
        self._root_path = path
        self._items = []
        self._filtered_items = []
        self._loaded_count = 0
        self._total_count = 0
        self._name_to_index.clear()
        if self._scandir_iter:
            try:
                self._scandir_iter.close()
            except:
                pass
        self._scandir_iter = None

        if path and os.path.isdir(path):
            try:
                self._scandir_iter = os.scandir(path)
                self._fetch_batch()
            except (PermissionError, OSError):
                pass
        self._apply_filter()
        self.endResetModel()

    def _fetch_batch(self):
        """Fetch the next batch of items from the directory."""
        if not self._scandir_iter:
            return

        count = 0
        try:
            for entry in self._scandir_iter:
                self._items.append(entry)
                self._name_to_index[entry.name] = len(self._items) - 1
                count += 1
                if count >= self.BATCH_SIZE:
                    break
            self._loaded_count = len(self._items)
            if count < self.BATCH_SIZE:
                # Exhausted iterator
                self._scandir_iter.close()
                self._scandir_iter = None
                self._total_count = self._loaded_count
        except (PermissionError, OSError):
            self._scandir_iter = None

    def _apply_filter(self):
        """Apply the current name filter to items and sort with folders first."""
        if not self._name_filter:
            self._filtered_items = self._items[:]
        else:
            filter_lower = self._name_filter.lower()
            self._filtered_items = [e for e in self._items if filter_lower in e.name.lower()]

        # Apply current sort
        self._sort_items()

    def _is_dir_safe(self, entry) -> bool:
        """Safely check if entry is a directory."""
        try:
            return entry.is_dir(follow_symlinks=False)
        except (PermissionError, OSError):
            return False

    def _get_entry_size(self, entry) -> int:
        """Get file size, 0 for directories."""
        try:
            if entry.is_file(follow_symlinks=False):
                return entry.stat(follow_symlinks=False).st_size
        except (PermissionError, OSError):
            pass
        return 0

    def _get_entry_mtime(self, entry) -> float:
        """Get modification time."""
        try:
            return entry.stat(follow_symlinks=False).st_mtime
        except (PermissionError, OSError):
            return 0

    def _get_entry_type(self, entry) -> str:
        """Get file type string."""
        if self._is_dir_safe(entry):
            return 'Folder'
        ext = os.path.splitext(entry.name)[1]
        return ext[1:].upper() + ' File' if ext else 'File'

    def _sort_items(self):
        """Sort filtered items with folders first, then by current sort column."""
        reverse = self._sort_order == Qt.DescendingOrder

        # Sort folders and files separately to maintain folders-first regardless of order
        folders = [e for e in self._filtered_items if self._is_dir_safe(e)]
        files = [e for e in self._filtered_items if not self._is_dir_safe(e)]

        # Sort each group
        if self._sort_column == 0:  # Name
            folders.sort(key=lambda e: e.name.lower(), reverse=reverse)
            files.sort(key=lambda e: e.name.lower(), reverse=reverse)
        elif self._sort_column == 1:  # Size
            folders.sort(key=lambda e: e.name.lower(), reverse=reverse)  # Folders by name
            files.sort(key=lambda e: self._get_entry_size(e), reverse=reverse)
        elif self._sort_column == 2:  # Type
            folders.sort(key=lambda e: e.name.lower(), reverse=reverse)  # Folders by name
            files.sort(key=lambda e: (self._get_entry_type(e).lower(), e.name.lower()), reverse=reverse)
        elif self._sort_column == 3:  # Date Modified
            folders.sort(key=lambda e: self._get_entry_mtime(e), reverse=reverse)
            files.sort(key=lambda e: self._get_entry_mtime(e), reverse=reverse)

        # Combine: folders always first
        self._filtered_items = folders + files

    def sort(self, column: int, order: Qt.SortOrder = Qt.AscendingOrder):
        """Sort by the specified column while keeping folders first."""
        self.beginResetModel()
        self._sort_column = column
        self._sort_order = order
        self._sort_items()
        self.endResetModel()

    def setNameFilter(self, filter_text: str):
        """Set a filter for file names."""
        self.beginResetModel()
        self._name_filter = filter_text
        self._apply_filter()
        self.endResetModel()

    def canFetchMore(self, parent: QModelIndex) -> bool:
        if parent.isValid():
            return False
        return self._scandir_iter is not None

    def fetchMore(self, parent: QModelIndex):
        if parent.isValid() or not self._scandir_iter:
            return

        old_count = len(self._filtered_items)
        self._fetch_batch()
        self._apply_filter()
        new_count = len(self._filtered_items)

        if new_count > old_count:
            self.beginInsertRows(QModelIndex(), old_count, new_count - 1)
            self.endInsertRows()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self._filtered_items)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(self.COLUMNS)

    def index(self, row: int, column: int, parent: QModelIndex = QModelIndex()) -> QModelIndex:
        if parent.isValid() or row < 0 or row >= len(self._filtered_items) or column < 0 or column >= len(self.COLUMNS):
            return QModelIndex()
        return self.createIndex(row, column, None)

    def indexFromName(self, name: str) -> QModelIndex:
        """Get model index for a file by name."""
        for i, entry in enumerate(self._filtered_items):
            if entry.name == name:
                return self.createIndex(i, 0, None)
        return QModelIndex()

    def parent(self, index: QModelIndex) -> QModelIndex:
        return QModelIndex()

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):
        if not index.isValid() or index.row() >= len(self._filtered_items):
            return None

        entry = self._filtered_items[index.row()]
        column = index.column()

        if role == Qt.DisplayRole:
            if column == 0:  # Name
                return entry.name
            elif column == 1:  # Size
                try:
                    if entry.is_file(follow_symlinks=False):
                        size = entry.stat(follow_symlinks=False).st_size
                        return self._format_size(size)
                    return ''
                except (PermissionError, OSError):
                    return ''
            elif column == 2:  # Type
                if entry.is_dir(follow_symlinks=False):
                    return 'Folder'
                ext = os.path.splitext(entry.name)[1]
                return ext[1:].upper() + ' File' if ext else 'File'
            elif column == 3:  # Date Modified
                try:
                    mtime = entry.stat(follow_symlinks=False).st_mtime
                    return datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M')
                except (PermissionError, OSError):
                    return ''

        elif role == Qt.DecorationRole and column == 0:
            try:
                return self._icon_provider.icon(QFileInfo(entry.path))
            except:
                return None

        return None

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            if 0 <= section < len(self.COLUMNS):
                return self.COLUMNS[section]
        return None

    def filePath(self, index: QModelIndex) -> str:
        """Return the file path for the given index."""
        if not index.isValid() or index.row() >= len(self._filtered_items):
            return ''
        return self._filtered_items[index.row()].path

    def isDir(self, index: QModelIndex) -> bool:
        """Return True if the index represents a directory."""
        if not index.isValid() or index.row() >= len(self._filtered_items):
            return False
        try:
            return self._filtered_items[index.row()].is_dir(follow_symlinks=False)
        except (PermissionError, OSError):
            return False

    def fileName(self, index: QModelIndex) -> str:
        """Return the file name for the given index."""
        if not index.isValid() or index.row() >= len(self._filtered_items):
            return ''
        return self._filtered_items[index.row()].name

    def size(self, index: QModelIndex) -> int:
        """Return the file size for the given index."""
        if not index.isValid() or index.row() >= len(self._filtered_items):
            return 0
        try:
            entry = self._filtered_items[index.row()]
            if entry.is_file(follow_symlinks=False):
                return entry.stat(follow_symlinks=False).st_size
        except (PermissionError, OSError):
            pass
        return 0

    @staticmethod
    def _format_size(size_bytes: int) -> str:
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.1f} PB"


@set_module_type('Widgets')
class FileTree(ConfigWidget):
    def __init__(self, parent, **kwargs):
        super().__init__(parent=parent)
        self.parent = parent

        # Get configuration parameters first
        self.files_in_tree = kwargs.get('files_in_tree', True)
        self.root_directory = kwargs.get('root_directory', Path.home())

        # Current directory state (use root directory as initial path)
        self.current_path = self.root_directory
        self.current_file = None
        self.history = [self.current_path]
        self.history_index = 0
        self.show_bookmarks = kwargs.get('show_bookmarks', True)

        # Performance optimizations
        self._icon_cache = {}
        self._dir_cache = {}
        self._size_cache = {}
        self._debounce_timer = QTimer()
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.timeout.connect(self._do_update_status_bar)

        # Bookmarks
        self.bookmarks = [
            Path.home(),
            Path.home() / "Desktop",
            Path.home() / "Documents",
            Path.home() / "Downloads",
        ]

        # Add system-specific bookmarks
        if sys.platform == "win32":
            self.bookmarks.extend([
                Path("C:"),
                Path("D:") if Path("D:").exists() else None,
            ])
        elif sys.platform == "darwin":  # macOS
            self.bookmarks.extend([
                Path("/Applications"),
                Path("/System"),
                Path("/Users"),
            ])
        else:  # Linux and other Unix-like systems
            self.bookmarks.extend([
                Path("/"),
                Path("/home"),
                Path("/usr"),
                Path("/opt"),
            ])

        # Remove None bookmarks and cache existence check
        self.bookmarks = [b for b in self.bookmarks if b and self._check_path_exists(b)]

        self.setup_ui()
        # self.load()

    def setup_ui(self):
        self.layout = CVBoxLayout(self)

        self.file_view = self.FileView(self)

        # Main content area
        self.horizontal_splitter = QSplitter(Qt.Horizontal)
        self.horizontal_splitter.setChildrenCollapsible(False)

        # Left panel (navigation)
        self.nav_panel = self.NavigationPanel(self)
        self.horizontal_splitter.addWidget(self.nav_panel)

        self.file_view_container = QWidget()
        self.file_view_layout = CVBoxLayout(self.file_view_container)
        # Path bar
        self.path_bar = self.PathBar(self)
        self.file_view_layout.addWidget(self.path_bar)

        # File view
        self.file_view_layout.addWidget(self.file_view)

        # Status bar
        self.status_bar = self.StatusBar(self)
        self.file_view_layout.addWidget(self.status_bar)

        # File preview
        self.file_preview = self.FilePreview(self)  # FilePreview(self)

        # Right panel (file view)
        self.vertical_splitter = QSplitter(Qt.Vertical)
        self.vertical_splitter.setChildrenCollapsible(False)
        self.vertical_splitter.addWidget(self.file_view_container)
        self.vertical_splitter.addWidget(self.file_preview)

        self.horizontal_splitter.addWidget(self.vertical_splitter)

        self.layout.addWidget(self.horizontal_splitter)

        # Set initial splitter sizes
        self.horizontal_splitter.setSizes([250, 750])
        # Set vertical splitter to show both file view and preview
        self.vertical_splitter.setSizes([500, 300])

        # Connect signals
        self.nav_panel.location_changed.connect(self.navigate_to)
        self.file_view.item_activated.connect(self.handle_item_activation)

    @lru_cache(maxsize=128)
    def _check_path_exists(self, path):
        """Cached path existence check."""
        return path.exists()

    def _clear_caches(self):
        """Clear all performance caches."""
        self._icon_cache.clear()
        self._dir_cache.clear()
        self._size_cache.clear()
        self._check_path_exists.cache_clear()

    def load(self):
        # Hide FileView if files_in_tree is enabled
        if self.files_in_tree:
            self.file_view_container.hide()

        self.navigate_to(self.current_path, update_page_path=False)
    
    def set_root_directory(self, path: Path):
        self.root_directory = path
        self.current_path = path
        self.history = [path]
        self.history_index = 0
        self.file_view.clear_views()
        self.nav_panel.clear_views()
        self.navigate_to(path)

    def navigate_to(self, path: Path, add_to_history: bool = True, update_page_path: bool = True):
        """Navigate to the specified path."""
        try:
            path = Path(path).resolve()
            if not self._check_path_exists(path):
                display_message(f"Path does not exist: {path}", "Error")
                return

            if not path.is_dir():
                # If it's a file, navigate to its parent directory and select it
                parent = path.parent
                if self._check_path_exists(parent) and parent.is_dir():
                    self.current_path = parent
                    if add_to_history:
                        self.add_to_history(parent)
                    if self.files_in_tree:
                        self.nav_panel.set_current_path(path)
                    else:
                        self.file_view.load_directory(parent)
                        self.file_view.select_item(path.name)
                    self.set_current_file(path)
                return

            self.current_path = path
            if add_to_history:
                self.add_to_history(path)

            # Update UI components
            self.path_bar.set_path(path)
            self.file_view.load_directory(path)
            self.nav_panel.set_current_path(path)
            self.update_toolbar_state()

            if update_page_path:
                QTimer.singleShot(0, self.update_page_map)

        except PermissionError:
            display_message(f"Permission denied: {path}", "Error")
        except Exception as e:
            display_message(f"Error navigating to {path}: {str(e)}", "Error")
    
    def set_current_file(self, file_path: Path):
        """Set the currently selected file."""
        self.current_file = file_path
        if file_path:
            self.file_preview.set_filepath(str(file_path))

    def add_to_history(self, path: Path):
        """Add path to navigation history."""
        # Remove any items after current position
        self.history = self.history[:self.history_index + 1]

        # Don't add duplicate of current item
        if not self.history or self.history[-1] != path:
            self.history.append(path)
            self.history_index = len(self.history) - 1

    def navigate_back(self):
        """Navigate to previous location in history."""
        if self.history_index > 0:
            self.history_index -= 1
            self.navigate_to(self.history[self.history_index], add_to_history=False)

    def navigate_forward(self):
        """Navigate to next location in history."""
        if self.history_index < len(self.history) - 1:
            self.history_index += 1
            self.navigate_to(self.history[self.history_index], add_to_history=False)

    def navigate_up(self):
        """Navigate to parent directory."""
        parent = self.current_path.parent
        if parent != self.current_path:  # Not at root
            self.navigate_to(parent)

    def update_toolbar_state(self):
        """Update toolbar button states based on current state."""
        self.nav_panel.back_btn.setEnabled(self.history_index > 0)
        self.nav_panel.forward_btn.setEnabled(self.history_index < len(self.history) - 1)
        self.nav_panel.up_btn.setEnabled(self.current_path.parent != self.current_path)

    def handle_item_activation(self, item_name: str):
        """Handle double-click or enter on a file/directory item."""
        item_path = self.current_path / item_name

        if item_path.is_dir():
            self.navigate_to(item_path)
        else:
            # Open file with system default application
            self.open_file(item_path)

    def open_file(self, file_path: Path):
        """Open file with system default application."""
        try:
            file_path_str = str(file_path)
            if sys.platform == "win32":
                os.startfile(file_path_str)
            elif sys.platform == "darwin":  # macOS
                os.system(f"open '{file_path_str}'")
            else:  # Linux and other Unix-like systems
                os.system(f"xdg-open '{file_path_str}'")
        except Exception as e:
            display_message(f"Error opening file: {str(e)}", "Error")

    def get_current_file(self):
        """Get the currently selected file, if any."""
        return self.current_file

    def update_status_bar(self):
        """Update status bar with current selection info."""
        # Use debouncing to avoid excessive updates
        self._debounce_timer.stop()
        self._debounce_timer.start(100)  # 100ms delay

    def _do_update_status_bar(self):
        """Actually perform the status bar update."""
        selected_items = self.file_view.get_selected_items()
        self.status_bar.update_selection_info(selected_items, self.current_path)
        
    def show_context_menu_for_path(self, view: QWidget, position: QPoint, index: QModelIndex = None):
        """Shared context menu handler for both FileView and NavigationPanel."""
        menu = QMenu(view)

        # Get file path from the appropriate model based on the view
        if index and index.isValid():
            # Check if view is from NavigationPanel (uses QFileSystemModel) or FileView (uses LazyFileSystemModel)
            if view == self.nav_panel.dir_tree:
                file_path = Path(self.nav_panel.dir_model.filePath(index))
            else:
                file_path = Path(self.file_view.file_model.filePath(index))

            if file_path.is_file():
                open_action = menu.addAction("Open")
                open_action.triggered.connect(lambda: self.open_file(file_path))

            rename_action = menu.addAction("Rename")
            rename_action.triggered.connect(lambda: self.file_view.rename_item(file_path))

            menu.addSeparator()

            copy_action = menu.addAction("Copy")
            copy_action.triggered.connect(lambda: self.file_view.copy_items([file_path]))

            cut_action = menu.addAction("Cut")
            cut_action.triggered.connect(lambda: self.file_view.cut_items([file_path]))

            menu.addSeparator()

            delete_action = menu.addAction("Delete")
            delete_action.triggered.connect(lambda: self.file_view.delete_items([file_path]))

            menu.addSeparator()

            properties_action = menu.addAction("Properties")
            properties_action.triggered.connect(lambda: self.file_view.show_properties(file_path))

        else:
            # Background (empty area)
            paste_action = menu.addAction("Paste")
            paste_action.setEnabled(QApplication.clipboard().mimeData().hasUrls())
            # paste_action.triggered.connect(self.file_view.paste_items)

            menu.addSeparator()

            new_folder_action = menu.addAction("New Folder")
            new_folder_action.triggered.connect(self.nav_panel.create_new_folder)

            refresh_action = menu.addAction("Refresh")
            refresh_action.triggered.connect(self.file_view.refresh)

        # Show at cursor position
        global_pos = view.mapToGlobal(position)
        menu.exec_(global_pos)

    class FilePreview(QWidget):
        """Tabbed container that loads studios based on file type."""
        def __init__(self, parent):
            super().__init__(parent)
            self.parent = parent
            self.layout = CVBoxLayout(self)
            self.open_files = {}  # {filepath: studio_widget}

            self.tab_widget = QTabWidget()
            self.tab_widget.setTabsClosable(True)
            self.tab_widget.setMovable(True)
            self.tab_widget.tabCloseRequested.connect(self.close_tab)
            self.tab_widget.currentChanged.connect(
                lambda: QTimer.singleShot(0, parent.update_page_map))
            self.layout.addWidget(self.tab_widget)

        def set_filepath(self, filepath: str):
            """Open a file in a tab, or focus existing tab."""
            # Check if already open
            if filepath in self.open_files:
                index = self.tab_widget.indexOf(self.open_files[filepath])
                if index >= 0:
                    self.tab_widget.setCurrentIndex(index)
                    return

            # Find studio for extension
            studios = system.manager.modules.get_modules_in_folder(
                'Studios',
                fetch_keys=('name', 'class',)
            )
            ext_studios = {}
            for _, studio_class in studios:
                if studio_class and hasattr(studio_class, 'associated_extensions'):
                    ext_studios.update({
                        ext.lower().lstrip('.'): studio_class
                        for ext in studio_class.associated_extensions
                    })
            ext = os.path.splitext(filepath)[1].lower().lstrip('.')
            studio_class = ext_studios.get(ext)
            if not studio_class:
                return

            # Create studio and open file
            studio = studio_class(self)
            studio.open_file(filepath)
            filename = os.path.basename(filepath)
            tab_index = self.tab_widget.addTab(studio, filename)
            self.tab_widget.setCurrentIndex(tab_index)
            self.open_files[filepath] = studio

        def close_tab(self, index):
            """Close a tab and clean up."""
            widget = self.tab_widget.widget(index)
            filepath = next(
                (fp for fp, w in self.open_files.items() if w is widget),
                None,
            )
            if filepath:
                del self.open_files[filepath]
            self.tab_widget.removeTab(index)

        def load(self):
            pass

    class NavigationPanel(QWidget):
        location_changed = Signal(Path)

        def __init__(self, parent):
            super().__init__(parent)
            self.parent = parent
            self.setup_ui()

        def setup_ui(self):
            self.layout = CVBoxLayout(self)

            # Toolbar row
            toolbar_row = CHBoxLayout()
            toolbar_row.setContentsMargins(0, 0, 0, 0)

            self.back_btn = IconButton(
                parent=self,
                icon_path=":/resources/icon-arrow-left.png",
                tooltip="Back"
            )
            self.forward_btn = IconButton(
                parent=self,
                icon_path=":/resources/icon-arrow-right.png",
                tooltip="Forward"
            )
            self.up_btn = IconButton(
                parent=self,
                icon_path=":/resources/icon-arrow-up.png",
                tooltip="Up"
            )
            self.back_btn.clicked.connect(self.parent.navigate_back)
            self.forward_btn.clicked.connect(self.parent.navigate_forward)
            self.up_btn.clicked.connect(self.parent.navigate_up)

            self.files_in_tree_btn = ToggleIconButton(
                parent=self,
                icon_path_checked=":/resources/icon-tree.png",
                icon_path_unchecked=":/resources/icon-list.png",
                tooltip="Toggle files in tree view",
                is_checked=self.parent.files_in_tree
            )
            self.files_in_tree_btn.clicked.connect(self.toggle_files_in_tree)

            self.new_folder_btn = IconButton(
                parent=self,
                icon_path=":/resources/icon-new-folder.png",
                tooltip="New Folder"
            )
            self.new_folder_btn.clicked.connect(self.create_new_folder)

            toolbar_row.addWidget(self.back_btn)
            toolbar_row.addWidget(self.forward_btn)
            toolbar_row.addWidget(self.up_btn)
            toolbar_row.addStretch()
            toolbar_row.addWidget(self.files_in_tree_btn)
            toolbar_row.addWidget(self.new_folder_btn)
            self.layout.addLayout(toolbar_row)

            # Search field
            self.search_field = QLineEdit()
            self.search_field.setPlaceholderText("Search files...")
            self.search_field.textChanged.connect(self.parent.file_view.filter_items)
            self.layout.addWidget(self.search_field)

            if self.parent.show_bookmarks:
                # Bookmarks section
                bookmarks_label = QLabel("Bookmarks")
                bookmarks_label.setStyleSheet("font-weight: bold; margin: 5px 0px;")

                # Directory tree section
                tree_label = QLabel("Computer")
                tree_label.setStyleSheet("font-weight: bold; margin: 15px 0px 5px 0px;")

            # Bookmarks list
            self.bookmarks_list = QListWidget()
            self.bookmarks_list.itemClicked.connect(self.on_bookmark_clicked)

            # Directory tree
            self.dir_tree = QTreeView()
            self.dir_tree.setHeaderHidden(True)
            self.dir_tree.setUniformRowHeights(True)  # Performance optimization
            self.dir_model = QFileSystemModel()
            # Disable features that slow down large directories
            self.dir_model.setOption(QFileSystemModel.DontWatchForChanges, True)
            self.dir_model.setOption(QFileSystemModel.DontResolveSymlinks, True)
            # set indent size to 20
            self.dir_tree.setIndentation(10)
            self.dir_tree.setModel(self.dir_model)

            # Set root directory
            root_path = str(self.parent.root_directory)
            self.dir_model.setRootPath(root_path)
            root_index = self.dir_model.index(root_path)
            self.dir_tree.setRootIndex(root_index)

            self.dir_tree.setContextMenuPolicy(Qt.CustomContextMenu)
            self.dir_tree.customContextMenuRequested.connect(self.show_context_menu)

            # Hide columns except name
            for i in range(1, self.dir_model.columnCount()):
                self.dir_tree.hideColumn(i)

            self.dir_tree.clicked.connect(self.on_tree_clicked)

            # Add splitter between bookmarks and directory tree
            from PySide6.QtWidgets import QSplitter, QWidget, QVBoxLayout

            self.splitter = QSplitter(Qt.Vertical)

            # Directory tree widget container
            dir_tree_widget = QWidget()
            dir_tree_layout = CVBoxLayout(dir_tree_widget)
            if self.parent.show_bookmarks:
                dir_tree_layout.addWidget(tree_label)
            dir_tree_layout.addWidget(self.dir_tree)
            # dir_tree_layout.addStretch(1)
            self.splitter.addWidget(dir_tree_widget)

            if self.parent.show_bookmarks:
                # Bookmarks widget container
                bookmarks_widget = QWidget()
                bookmarks_layout = CVBoxLayout(bookmarks_widget)
                bookmarks_layout.addWidget(bookmarks_label)
                bookmarks_layout.addWidget(self.bookmarks_list)
                # bookmarks_layout.addStretch(1)
                self.splitter.addWidget(bookmarks_widget)

            self.layout.addWidget(self.splitter)

            self.load()
        
        def load(self):
            # Set filter based on files_in_tree setting
            if self.parent.files_in_tree:
                # Show both directories and files
                self.dir_model.setFilter(QDir.AllEntries | QDir.NoDotAndDotDot)
            else:
                # Show only directories
                self.dir_model.setFilter(QDir.Dirs | QDir.NoDotAndDotDot)

            self.populate_bookmarks()

        def populate_bookmarks(self):
            """Populate the bookmarks list."""
            self.bookmarks_list.clear()
            folder_icon = self.get_folder_icon()  # Cache icon outside loop
            for bookmark in self.parent.bookmarks:
                if self.parent._check_path_exists(bookmark):
                    item = QListWidgetItem(bookmark.name or str(bookmark))
                    item.setData(Qt.UserRole, bookmark)
                    item.setIcon(folder_icon)
                    self.bookmarks_list.addItem(item)

        def get_folder_icon(self) -> QIcon:
            """Get the standard folder icon with caching."""
            # use_icon_path = ':/resources/icon-folder.png'
            # folder_pixmap = colorize_pixmap(QPixmap(use_icon_path))
            if 'folder' not in self.parent._icon_cache:
                self.parent._icon_cache['folder'] = self.style().standardIcon(QStyle.SP_DirIcon)
            return self.parent._icon_cache['folder']

        def on_bookmark_clicked(self, item: QListWidgetItem):
            """Handle bookmark selection."""
            path = item.data(Qt.UserRole)
            if path and path.exists():
                self.location_changed.emit(path)

        def on_tree_clicked(self, index: QModelIndex):
            """Handle directory tree selection."""
            path = Path(self.dir_model.filePath(index))
            if path.is_dir():
                # Only emit location_changed if files_in_tree is False
                # When files_in_tree is True, we show files in NavigationPanel
                if not self.parent.files_in_tree:
                    self.location_changed.emit(path)
            else:
                # Update current_file when file is selected in tree
                self.parent.set_current_file(path)

        def set_current_path(self, path: Path):
            """Update the navigation panel to reflect current path."""
            # Only set path if it's within the root directory
            if not str(path).startswith(str(self.parent.root_directory)):
                return

            # Expand tree to show current path
            index = self.dir_model.index(str(path))
            if index.isValid():
                self.dir_tree.setCurrentIndex(index)
                # Expand parent directories up to root
                parent_index = index.parent()
                while parent_index.isValid() and self.dir_model.filePath(parent_index) != str(self.parent.root_directory):
                    self.dir_tree.expand(parent_index)
                    parent_index = parent_index.parent()
        
        def show_context_menu(self, position: QPoint):
            index = self.dir_tree.indexAt(position)
            self.parent.show_context_menu_for_path(self.dir_tree, position, index)

        def toggle_files_in_tree(self):
            """Toggle the files_in_tree setting and refresh the navigation panel."""
            self.parent.files_in_tree = not self.parent.files_in_tree

            if self.parent.files_in_tree:
                self.dir_model.setFilter(QDir.AllEntries | QDir.NoDotAndDotDot)
                self.parent.file_view_container.hide()
            else:
                self.dir_model.setFilter(QDir.Dirs | QDir.NoDotAndDotDot)
                self.parent.file_view_container.show()

            self.parent.navigate_to(self.parent.current_path, add_to_history=False)

        def create_new_folder(self):
            """Create a new folder in the current directory."""
            name, ok = QInputDialog.getText(
                self, "New Folder", "Enter folder name:"
            )
            if ok and name.strip():
                folder_path = self.parent.current_path / name.strip()
                try:
                    folder_path.mkdir(exist_ok=False)
                    self.parent.file_view.load_directory(self.parent.current_path)
                except FileExistsError:
                    display_message(f"Folder '{name}' already exists", "Error")
                except Exception as e:
                    display_message(f"Error creating folder: {str(e)}", "Error")

        def clear_views(self):
            """Clear and reset the navigation panel views."""
            # Don't set model to None, just update the root path
            # Setting to None causes issues when navigate_to is called after
            self.bookmarks_list.clear()
            # Reset the model to a new root
            root_path = str(self.parent.root_directory)
            self.dir_model.setRootPath(root_path)
            root_index = self.dir_model.index(root_path)
            if root_index.isValid():
                self.dir_tree.setRootIndex(root_index)

    class PathBar(QWidget):
        def __init__(self, parent):
            super().__init__(parent)
            self.parent = parent
            self.current_path = None
            self.setup_ui()

        def setup_ui(self):
            self.layout = CHBoxLayout(self)
            self.layout.setContentsMargins(5, 2, 5, 2)

            # Path display/edit
            self.path_edit = QLineEdit()
            self.path_edit.returnPressed.connect(self.navigate_to_typed_path)
            self.layout.addWidget(self.path_edit)

            # Home button
            self.home_btn = IconButton(
                parent=self,
                icon_path=":/resources/icon-home.png",
                tooltip="Home"
            )
            self.home_btn.clicked.connect(lambda: self.parent.navigate_to(Path.home()))
            self.layout.addWidget(self.home_btn)

        def set_path(self, path: Path):
            """Set the current path in the path bar."""
            self.current_path = path
            self.path_edit.setText(str(path))

        def navigate_to_typed_path(self):
            """Navigate to the path typed in the path bar."""
            path_str = self.path_edit.text().strip()
            if path_str:
                try:
                    path = Path(path_str).expanduser().resolve()
                    self.parent.navigate_to(path)
                except Exception as e:
                    display_message(f"Invalid path: {str(e)}", "Error")
                    # Reset to current path
                    if self.current_path:
                        self.path_edit.setText(str(self.current_path))

    class FileView(QWidget):
        item_activated = Signal(str)
        selection_changed = Signal()

        def __init__(self, parent):
            super().__init__(parent)
            self.parent = parent
            self.current_directory = None
            self.view_mode = "Details"
            self.filter_text = ""
            self.setup_ui()

        def setup_ui(self):
            self.layout = CVBoxLayout(self)

            # Lazy-loading file model for performance with large directories
            self.file_model = LazyFileSystemModel(self)

            # Create different views
            self.detail_view = QTreeView()
            self.list_view = QListView()
            self.grid_view = QListView()

            # Configure detail view
            self.detail_view.setModel(self.file_model)
            self.detail_view.setRootIsDecorated(False)
            self.detail_view.setUniformRowHeights(True)
            self.detail_view.setSortingEnabled(True)
            self.detail_view.sortByColumn(0, Qt.AscendingOrder)
            self.detail_view.setContextMenuPolicy(Qt.CustomContextMenu)
            self.detail_view.customContextMenuRequested.connect(self.show_context_menu)
            self.detail_view.doubleClicked.connect(self.on_item_activated)
            self.detail_view.selectionModel().selectionChanged.connect(
                lambda: (self.parent.update_status_bar(), self.update_current_file())
            )

            # Configure list view
            self.list_view.setModel(self.file_model)
            self.list_view.setViewMode(QListView.ListMode)
            self.list_view.setUniformItemSizes(True)
            self.list_view.setLayoutMode(QListView.Batched)
            self.list_view.setBatchSize(100)
            self.list_view.setContextMenuPolicy(Qt.CustomContextMenu)
            self.list_view.customContextMenuRequested.connect(self.show_context_menu)
            self.list_view.doubleClicked.connect(self.on_item_activated)
            self.list_view.selectionModel().selectionChanged.connect(
                lambda: (self.parent.update_status_bar(), self.update_current_file())
            )

            # Configure grid view
            self.grid_view.setModel(self.file_model)
            self.grid_view.setViewMode(QListView.IconMode)
            self.grid_view.setResizeMode(QListView.Adjust)
            self.grid_view.setUniformItemSizes(True)
            self.grid_view.setLayoutMode(QListView.Batched)
            self.grid_view.setBatchSize(100)
            self.grid_view.setContextMenuPolicy(Qt.CustomContextMenu)
            self.grid_view.customContextMenuRequested.connect(self.show_context_menu)
            self.grid_view.doubleClicked.connect(self.on_item_activated)
            self.grid_view.selectionModel().selectionChanged.connect(
                lambda: (self.parent.update_status_bar(), self.update_current_file())
            )

            # Stack the views
            self.stacked_widget = QStackedWidget()
            self.stacked_widget.addWidget(self.detail_view)  # 0
            self.stacked_widget.addWidget(self.list_view)    # 1
            self.stacked_widget.addWidget(self.grid_view)    # 2

            self.layout.addWidget(self.stacked_widget)

            # Enable drag and drop
            self.setAcceptDrops(True)
            for view in [self.detail_view, self.list_view, self.grid_view]:
                view.setDragDropMode(QAbstractItemView.DragDrop)
                view.setDefaultDropAction(Qt.MoveAction)

        def set_view_mode(self, mode: str):
            """Set the view mode (List, Grid, Details)."""
            self.view_mode = mode
            if mode == "Details":
                self.stacked_widget.setCurrentIndex(0)
            elif mode == "List":
                self.stacked_widget.setCurrentIndex(1)
            elif mode == "Grid":
                self.stacked_widget.setCurrentIndex(2)

        def get_current_view(self):
            """Get the currently active view widget."""
            current_index = self.stacked_widget.currentIndex()
            if current_index == 0:
                return self.detail_view
            elif current_index == 1:
                return self.list_view
            else:
                return self.grid_view

        def load_directory(self, path: Path, force=False):
            """Load the specified directory with lazy loading."""
            if not force and self.current_directory == path:
                return  # Already loaded

            self.current_directory = path
            self.file_model.setRootPath(str(path))

        def refresh(self):
            """Refresh the current directory."""
            if self.current_directory:
                self.load_directory(self.current_directory, force=True)

        def filter_items(self, text: str):
            """Filter items based on search text."""
            text = text.strip()
            if self.filter_text == text:
                return  # No change, skip update

            self.filter_text = text
            self.file_model.setNameFilter(text)

        def select_item(self, name: str):
            """Select an item by name."""
            if not self.current_directory:
                return

            index = self.file_model.indexFromName(name)
            if index.isValid():
                current_view = self.get_current_view()
                current_view.setCurrentIndex(index)
                current_view.scrollTo(index)

        def get_selected_items(self) -> List[Path]:
            """Get list of selected item paths."""
            current_view = self.get_current_view()
            selected_indexes = current_view.selectionModel().selectedIndexes()

            # Filter to only name column for detail view
            if current_view == self.detail_view:
                selected_indexes = [idx for idx in selected_indexes if idx.column() == 0]

            selected_paths = []
            for index in selected_indexes:
                file_path = self.file_model.filePath(index)
                selected_paths.append(Path(file_path))

            return selected_paths

        def update_current_file(self):
            """Update the current_file when selection changes."""
            selected_items = self.get_selected_items()

            if len(selected_items) == 1:
                selected_path = selected_items[0]
                if selected_path.is_file():
                    self.parent.set_current_file(selected_path)
                else:
                    # If a directory is selected, clear current_file
                    self.parent.set_current_file(None)
            else:
                # If multiple items or no items selected, clear current_file
                self.parent.set_current_file(None)

        def on_item_activated(self, index: QModelIndex):
            """Handle item activation (double-click)."""
            file_path = self.file_model.filePath(index)
            file_name = Path(file_path).name

            # # Update current_file if it's a file
            # path_obj = Path(file_path)
            # if path_obj.is_file():
            #     self.parent.current_file = path_obj

            self.item_activated.emit(file_name)

        def show_context_menu(self, position: QPoint):
            current_view = self.get_current_view()
            index = current_view.indexAt(position)
            self.parent.show_context_menu_for_path(current_view, position, index)

            # """Show context menu for file operations."""
            # current_view = self.get_current_view()
            # index = current_view.indexAt(position)

            # menu = QMenu(self)

            # if index.isValid():
            #     # Item-specific actions
            #     file_path = Path(self.file_model.filePath(index))

            #     if file_path.is_file():
            #         open_action = menu.addAction("Open")
            #         open_action.triggered.connect(lambda: self.parent.open_file(file_path))

            #     rename_action = menu.addAction("Rename")
            #     rename_action.triggered.connect(lambda: self.rename_item(file_path))

            #     menu.addSeparator()

            #     copy_action = menu.addAction("Copy")
            #     copy_action.triggered.connect(lambda: self.copy_items([file_path]))

            #     cut_action = menu.addAction("Cut")
            #     cut_action.triggered.connect(lambda: self.cut_items([file_path]))

            #     menu.addSeparator()

            #     delete_action = menu.addAction("Delete")
            #     delete_action.triggered.connect(lambda: self.delete_items([file_path]))

            #     menu.addSeparator()

            #     properties_action = menu.addAction("Properties")
            #     properties_action.triggered.connect(lambda: self.show_properties(file_path))
            # else:
            #     # Background context menu
            #     paste_action = menu.addAction("Paste")
            #     paste_action.setEnabled(QApplication.clipboard().mimeData().hasUrls())
            #     # paste_action.triggered.connect(self.paste_items)

            #     menu.addSeparator()

            #     new_folder_action = menu.addAction("New Folder")
            #     new_folder_action.triggered.connect(self.parent.toolbar.create_new_folder)

            #     refresh_action = menu.addAction("Refresh")
            #     refresh_action.triggered.connect(lambda: self.load_directory(self.current_directory))

            # # Show menu at cursor position
            # global_position = current_view.mapToGlobal(position)
            # menu.exec_(global_position)

        def rename_item(self, file_path: Path):
            """Rename a file or directory."""
            old_name = file_path.name
            new_name, ok = QInputDialog.getText(
                self, "Rename", "Enter new name:", text=old_name
            )

            if ok and new_name.strip() and new_name != old_name:
                new_path = file_path.parent / new_name.strip()
                try:
                    file_path.rename(new_path)
                    self.refresh()
                except Exception as e:
                    display_message(f"Error renaming: {str(e)}", "Error")

        def copy_items(self, file_paths: List[Path]):
            """Copy items to clipboard."""
            urls = [QUrl.fromLocalFile(str(path)) for path in file_paths]
            mime_data = QMimeData()
            mime_data.setUrls(urls)
            QApplication.clipboard().setMimeData(mime_data)

        def cut_items(self, file_paths: List[Path]):
            """Cut items to clipboard."""
            # TODO: Implement cut operation (requires tracking cut state)
            self.copy_items(file_paths)

        def delete_items(self, file_paths: List[Path]):
            """Delete files/directories."""
            if not file_paths:
                return

            # Confirm deletion
            if len(file_paths) == 1:
                message = f"Are you sure you want to delete '{file_paths[0].name}'?"
            else:
                message = f"Are you sure you want to delete {len(file_paths)} items?"

            reply = display_message_box(
                icon=QMessageBox.Question,
                title="Confirm Delete",
                text=message,
                buttons=QMessageBox.Yes | QMessageBox.No
            )

            if reply == QMessageBox.Yes:
                errors = []
                for file_path in file_paths:
                    try:
                        if file_path.is_dir():
                            shutil.rmtree(file_path)
                        else:
                            file_path.unlink()
                    except Exception as e:
                        errors.append(f"{file_path.name}: {str(e)}")

                if errors:
                    display_message(
                        "Some items could not be deleted:\n" + "\n".join(errors),
                        "Deletion Errors"
                    )

                self.refresh()
                # Refresh nav panel (QFileSystemModel has DontWatchForChanges)
                root_path = str(self.parent.root_directory)
                self.parent.nav_panel.dir_model.setRootPath('')
                self.parent.nav_panel.dir_model.setRootPath(root_path)

        def show_properties(self, file_path: Path):
            """Show file/directory properties dialog."""
            dialog = FilePropertiesDialog(file_path, self)
            dialog.exec_()
        
        def clear_views(self):
            """Clear the file views by resetting the model."""
            self.file_model.setRootPath(None)
            self.stacked_widget.setCurrentIndex(0)
            self.current_directory = None

    class StatusBar(QWidget):
        def __init__(self, parent):
            super().__init__(parent)
            self.parent = parent
            self.setup_ui()

        def setup_ui(self):
            self.layout = CHBoxLayout(self)
            self.layout.setContentsMargins(5, 2, 5, 2)

            self.status_label = QLabel()
            self.layout.addWidget(self.status_label)

            self.layout.addStretch()

            self.selection_label = QLabel()
            self.layout.addWidget(self.selection_label)

        def update_selection_info(self, selected_items: List[Path], current_path: Path):
            """Update status bar with selection and directory info."""
            try:
                model = self.parent.file_view.file_model

                # Directory info - use model's loaded row count
                if current_path and current_path.is_dir():
                    total_rows = model.rowCount()
                    # For large directories, just show total count
                    if total_rows > 500:
                        more = " +" if model.canFetchMore(QModelIndex()) else ""
                        self.status_label.setText(f"{total_rows}{more} items")
                    else:
                        # Count dirs and files separately for smaller directories
                        dirs = 0
                        files = 0
                        for row in range(total_rows):
                            idx = model.index(row, 0)
                            if model.isDir(idx):
                                dirs += 1
                            else:
                                files += 1
                        dir_text = f"{dirs} folder{'s' if dirs != 1 else ''}, {files} file{'s' if files != 1 else ''}"
                        self.status_label.setText(dir_text)

                # Selection info
                if not selected_items:
                    self.selection_label.setText("")
                elif len(selected_items) == 1:
                    item = selected_items[0]
                    if item.is_dir():
                        self.selection_label.setText("1 folder selected")
                    else:
                        try:
                            size_bytes = item.stat().st_size
                            size = self.format_size(size_bytes)
                            self.selection_label.setText(f"1 file selected ({size})")
                        except (PermissionError, OSError):
                            self.selection_label.setText("1 file selected")
                else:
                    count = len(selected_items)
                    self.selection_label.setText(f"{count} items selected")

            except Exception:
                self.status_label.setText("Error reading directory")
                self.selection_label.setText("")

        @staticmethod
        def format_size(size_bytes: int) -> str:
            """Format file size in human readable format."""
            if size_bytes == 0:
                return "0 B"
            for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
                if size_bytes < 1024.0:
                    return f"{size_bytes:.1f} {unit}"
                size_bytes /= 1024.0
            return f"{size_bytes:.1f} PB"


class FilePropertiesDialog(QDialog):
    """Dialog to display file/directory properties."""

    def __init__(self, file_path: Path, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.Window
            | Qt.WindowTitleHint
            | Qt.WindowSystemMenuHint
            | Qt.WindowCloseButtonHint
            | Qt.WindowStaysOnTopHint
        )
        self.file_path = file_path
        self.setWindowTitle(f"Properties - {file_path.name}")
        self.setModal(True)
        self.resize(400, 300)
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)

        # File icon and name
        header_layout = QHBoxLayout()

        # Get file icon with caching
        icon_key = f"icon_{self.file_path.suffix}_{self.file_path.is_dir()}"
        if icon_key not in getattr(self.parent(), '_icon_cache', {}):
            icon_provider = QFileIconProvider()
            icon = icon_provider.icon(QFileInfo(str(self.file_path)))
            if hasattr(self.parent(), '_icon_cache'):
                self.parent()._icon_cache[icon_key] = icon
        else:
            icon = self.parent()._icon_cache[icon_key]

        icon_label = QLabel()
        icon_label.setPixmap(icon.pixmap(48, 48))
        icon_label.setFixedSize(48, 48)

        name_label = QLabel(self.file_path.name)
        name_label.setFont(QFont("", 12, QFont.Bold))

        header_layout.addWidget(icon_label)
        header_layout.addWidget(name_label)
        header_layout.addStretch()

        layout.addLayout(header_layout)

        # Properties table
        props_widget = QWidget()
        props_layout = QFormLayout(props_widget)

        try:
            stat_info = self.file_path.stat()

            # Basic info
            props_layout.addRow("Name:", QLabel(self.file_path.name))
            props_layout.addRow("Location:", QLabel(str(self.file_path.parent)))

            if self.file_path.is_file():
                props_layout.addRow("Type:", QLabel("File"))
                size = self.format_size(stat_info.st_size)
                props_layout.addRow("Size:", QLabel(size))
            else:
                props_layout.addRow("Type:", QLabel("Directory"))
                # Calculate directory size with caching and optimization
                size_label = QLabel("Calculating...")
                props_layout.addRow("Size:", size_label)

                # Use QTimer to calculate size asynchronously to avoid blocking UI
                self._calculate_dir_size_async(size_label)

            # Timestamps
            created_time = datetime.fromtimestamp(stat_info.st_ctime).strftime('%Y-%m-%d %H:%M:%S')
            modified_time = datetime.fromtimestamp(stat_info.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
            accessed_time = datetime.fromtimestamp(stat_info.st_atime).strftime('%Y-%m-%d %H:%M:%S')

            props_layout.addRow("Created:", QLabel(created_time))
            props_layout.addRow("Modified:", QLabel(modified_time))
            props_layout.addRow("Accessed:", QLabel(accessed_time))

            # Permissions
            permissions = stat.filemode(stat_info.st_mode)
            props_layout.addRow("Permissions:", QLabel(permissions))

        except Exception as e:
            props_layout.addRow("Error:", QLabel(str(e)))

        layout.addWidget(props_widget)

        # Close button
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        button_layout.addWidget(close_btn)

        layout.addLayout(button_layout)

    def _calculate_dir_size_async(self, label):
        """Calculate directory size asynchronously."""
        try:
            # Quick estimate first
            quick_size = 0
            file_count = 0
            for item in self.file_path.iterdir():
                if item.is_file():
                    quick_size += item.stat().st_size
                    file_count += 1
                if file_count > 100:  # Limit for performance
                    label.setText(f"{self.format_size(quick_size)}+ (approx)")
                    return

            if file_count <= 100:
                # Calculate exact size for smaller directories
                total_size = sum(f.stat().st_size for f in self.file_path.rglob('*') if f.is_file())
                label.setText(self.format_size(total_size))
            else:
                label.setText(f"{self.format_size(quick_size)}+ (large dir)")
        except:
            label.setText("Unable to calculate")

    @staticmethod
    def format_size(size_bytes: int) -> str:
        """Format file size in human readable format."""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.1f} PB"