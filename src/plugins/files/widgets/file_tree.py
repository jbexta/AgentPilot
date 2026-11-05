import asyncio
import heapq
import os
import sys
import shutil
import stat
from datetime import datetime
from pathlib import Path
from typing import List
from functools import lru_cache

import qasync
import shiboken6
from PySide6.QtWidgets import *
from PySide6.QtCore import *
from PySide6.QtGui import *

from gui.gui_utils.custom_menu import CustomMenu
from gui.gui_utils.helpers import clear_layout
from gui.gui_utils.icon_button import IconButton
from gui.gui_utils.layouts import CHBoxLayout, CVBoxLayout
from gui import system
from gui.widgets.config_joined import ConfigJoined
from gui.widgets.config_widget import ConfigWidget
from utils.helpers import display_message, display_message_box, format_llm_tools, get_text, llm_tool, readable_class_name, set_module_type


class ThumbnailIconProvider(QFileIconProvider):
    def __init__(self):
        super().__init__()
        self.image_suffixes = {
            bytes(fmt).decode() for fmt in QImageReader.supportedImageFormats()
        }

    def icon(self, info):
        if isinstance(info, QFileInfo) and info.suffix().lower() in self.image_suffixes:
            return QIcon(info.filePath())
        return super().icon(info)


class ColoredFileSystemModel(QFileSystemModel):
    def __init__(self, color_for):
        super().__init__()
        self.color_for = color_for

    def data(self, index, role=Qt.DisplayRole):
        if role == Qt.ForegroundRole and index.column() == 0:
            return self.color_for(self.filePath(index), self.isDir(index))
        return super().data(index, role)


class LazyFileSystemModel(QAbstractItemModel):
    """A lazy-loading file system model that loads items in batches for performance."""

    BATCH_SIZE = 200
    COLUMNS = ['Name', 'Size', 'Type', 'Date Modified']

    def __init__(self, parent=None, media_thumbnails=False):
        super().__init__(parent)
        self._root_path = None
        self._items = []  # List of DirEntry objects
        self._filtered_items = []  # Filtered view of items
        self._loaded_count = 0
        self._total_count = 0
        self._scandir_iter = None
        self._icon_provider = ThumbnailIconProvider() if media_thumbnails else QFileIconProvider()
        self._name_filter = ''
        self._name_to_index = {}  # Cache for quick lookups
        self._sort_column = 0  # Default sort by name
        self._sort_order = Qt.AscendingOrder
        self.show_hidden = False
        self.color_for = None

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
        items = self._items
        if not self.show_hidden:
            items = [e for e in items if not e.name.startswith('.')]
        if not self._name_filter:
            self._filtered_items = items[:]
        else:
            filter_lower = self._name_filter.lower()
            self._filtered_items = [e for e in items if filter_lower in e.name.lower()]

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

        elif role == Qt.ForegroundRole and column == 0 and self.color_for:
            return self.color_for(entry.path, self._is_dir_safe(entry))

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


RECENT_SKIP_DIRS = {'node_modules', '__pycache__', 'venv', 'site-packages'}


def scan_recent_files(root: Path, extensions: set, max_files=25, max_entries=50000):
    """Return the most recently modified (mtime, path) pairs under root."""
    found = []
    visited = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            d for d in dirnames
            if not d.startswith('.') and d not in RECENT_SKIP_DIRS
        ]
        for name in filenames:
            visited += 1
            ext = os.path.splitext(name)[1].lower().lstrip('.')
            if name.startswith('.') or ext not in extensions:
                continue
            path = os.path.join(dirpath, name)
            try:
                found.append((os.path.getmtime(path), path))
            except OSError:
                continue
        if visited > max_entries:
            break
    return heapq.nlargest(max_files, found)


def search_in_files(root: Path, query: str, show_hidden=False,
                    max_results=1000, max_file_size=2_000_000):
    """Return [(path, [(line_no, line)])] for files under root containing
    query, case-insensitive."""
    query = query.lower()
    results = []
    match_count = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(
            d for d in dirnames
            if (show_hidden or not d.startswith('.'))
            and d not in RECENT_SKIP_DIRS
        )
        for name in sorted(filenames):
            if not show_hidden and name.startswith('.'):
                continue
            path = os.path.join(dirpath, name)
            try:
                if os.path.getsize(path) > max_file_size:
                    continue
                with open(path, 'rb') as f:
                    data = f.read()
            except OSError:
                continue
            if b'\0' in data[:8192]:
                continue
            text = data.decode('utf-8', errors='replace')
            if query not in text.lower():
                continue
            matches = [
                (line_no, line.strip())
                for line_no, line in enumerate(text.splitlines(), 1)
                if query in line.lower()
            ]
            results.append((Path(path), matches))
            match_count += len(matches)
            if match_count >= max_results:
                return results
    return results


class FileTreeExtension(QWidget):
    """Base of Widgets modules that add features to every FileTree. One is
    created per FileTree and shown in its navigation toolbar."""

    def __init__(self, tree):
        super().__init__(tree)
        self.tree = tree

    def refresh(self):
        pass

    def item_color(self, path, is_dir):
        return None

    def add_context_actions(self, menu, paths):
        pass

    def options_menu_schema(self):
        return []

    def get_agent_visualisation(self, refs):
        return format_llm_tools(self, refs)


@set_module_type('Widgets')
class FileTree(ConfigWidget):
    CUT_MIME_TYPE = 'application/x-agentpilot-cut'

    def __init__(self, parent, **kwargs):
        super().__init__(parent=parent)
        self.parent = parent

        # Get configuration parameters first
        self.fixed_directory = kwargs.get('fixed_directory', False)
        self.files_in_tree = kwargs.get('files_in_tree', True)
        self.root_directory = kwargs.get('root_directory', Path.home())
        self.media_thumbnails = kwargs.get('media_thumbnails', False)
        self.show_hidden = kwargs.get('show_hidden', False)

        # Current directory state (use root directory as initial path)
        self.current_path = self.root_directory
        self.current_file = None
        self.history = [self.current_path]
        self.history_index = 0
        self.show_bookmarks = kwargs.get('show_bookmarks', True) and not self.fixed_directory

        # Performance optimizations
        self._icon_cache = {}
        self._dir_cache = {}
        self._size_cache = {}
        self._debounce_timer = QTimer()
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.timeout.connect(self._do_update_status_bar)

        widget_modules = system.manager.modules.get_modules_in_folder(
            'Widgets', fetch_keys=('name', 'class'))
        self.extensions = [
            cls(self) for _, cls in widget_modules
            if isinstance(cls, type) and issubclass(cls, FileTreeExtension)
        ]

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

        if self.fixed_directory:
            self.path_bar.hide()
            self.nav_panel.back_btn.hide()
            self.nav_panel.forward_btn.hide()
            self.nav_panel.up_btn.hide()

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
        if self.file_preview.recent_files.isVisible():
            self.file_preview.recent_files.refresh()
    
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
                    self.refresh_extensions()
                return

            self.current_path = path
            if add_to_history:
                self.add_to_history(path)

            # Update UI components
            self.path_bar.set_path(path)
            self.file_view.load_directory(path)
            self.nav_panel.set_current_path(path)
            self.update_toolbar_state()
            self.refresh_extensions()

            if update_page_path:
                self.defer_update_page_map()

        except PermissionError:
            display_message(f"Permission denied: {path}", "Error")
        except Exception as e:
            display_message(f"Error navigating to {path}: {str(e)}", "Error")
    
    def refresh_extensions(self):
        for extension in self.extensions:
            extension.refresh()

    def item_color(self, path, is_dir):
        return next((
            color for extension in self.extensions
            if (color := extension.item_color(path, is_dir))
        ), None)

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
            if not self.fixed_directory:
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

    def get_agent_visualisation(self, refs):
        from textwrap import indent
        lines = [f'{readable_class_name(self)}:']
        tools = format_llm_tools(self, refs)
        if tools:
            lines.append(indent(tools, '    '))
        lines.append(f'    Cwd: {self.current_path}')
        for extension in self.extensions:
            if extension.isVisible():
                sub = extension.get_agent_visualisation(refs)
                if sub:
                    lines.append(indent(sub, '    '))
        open_files = self.file_preview.open_files
        if open_files:
            lines.append('    Open files:')
        current_tab = self.file_preview.tab_widget.currentWidget()
        for filepath, studio in sorted(open_files.items(), key=lambda f: f[1] is current_tab):
            is_current = studio is current_tab
            lines.append(f"        - {filepath}{' (current)' if is_current else ''}")
            if not is_current:
                continue
            if hasattr(studio, 'get_agent_visualisation'):
                sub = studio.get_agent_visualisation(refs)
            else:
                sub = format_llm_tools(studio, refs)
            if sub:
                lines.append(indent(sub, ' ' * 12))
        return '\n'.join(lines)

    @staticmethod
    def _agent_error(message):
        display_message(message, "Error")
        raise ValueError(message)

    def _resolve_agent_path(self, path):
        resolved = (Path(self.current_path) / path).resolve()
        if not resolved.is_relative_to(Path(self.root_directory).resolve()):
            self._agent_error(f"Path is outside the root directory: {resolved}")
        if not resolved.exists():
            self._agent_error(f"Path does not exist: {resolved}")
        return resolved

    @llm_tool(
        description='List the entries of a directory',
        params={'path': 'Directory to list, absolute or relative to Cwd'},
    )
    def list_directory(self, path: str = '.'):
        directory = self._resolve_agent_path(path)
        if not directory.is_dir():
            self._agent_error(f"Not a directory: {directory}")
        entries = sorted(
            directory.iterdir(),
            key=lambda p: (not p.is_dir(), p.name.lower()),
        )
        return '\n'.join(
            f'{p.name}/' if p.is_dir() else p.name for p in entries
        )

    @llm_tool(
        description='Select a file or directory in the tree; '
                    'files open in a preview tab',
        params={'path': 'File or directory, absolute or relative to Cwd'},
    )
    def select(self, path: str):
        target = self._resolve_agent_path(path)
        self.nav_panel.set_current_path(target)
        index = self.nav_panel.dir_model.index(str(target))
        if index.isValid():
            self.nav_panel.on_tree_current_changed(index, None)
        elif target.is_file():
            self.set_current_file(target)

    def get_page_state(self):
        expanded = []
        model = self.nav_panel.dir_model
        tree = self.nav_panel.dir_tree
        def _collect_expanded(parent_index):
            for row in range(model.rowCount(parent_index)):
                index = model.index(row, 0, parent_index)
                if tree.isExpanded(index):
                    expanded.append(model.filePath(index))
                    _collect_expanded(index)
        _collect_expanded(tree.rootIndex())
        return {
            'current_path': str(self.current_path),
            'current_file': str(self.current_file) if self.current_file else None,
            'expanded': expanded,
            'open_files': list(self.file_preview.open_files.keys()),
            'active_tab': self.file_preview.tab_widget.currentIndex(),
        }

    def set_page_state(self, state):
        if not isinstance(state, dict):
            state = {'current_path': str(state)}
        dir_path = state.get('current_path')
        if dir_path:
            self.navigate_to(Path(dir_path), update_page_path=False)
        for folder_path in state.get('expanded', []):
            index = self.nav_panel.dir_model.index(folder_path)
            if index.isValid():
                self.nav_panel.dir_tree.expand(index)
        for filepath in state.get('open_files', []):
            self.file_preview.set_filepath(filepath)
        active_tab = state.get('active_tab', -1)
        if active_tab >= 0:
            self.file_preview.tab_widget.setCurrentIndex(active_tab)
        current_file = state.get('current_file')
        if current_file:
            self.current_file = Path(current_file)
        if current_file and self.files_in_tree:
            tree = self.nav_panel.dir_tree
            model = self.nav_panel.dir_model
            index = model.index(current_file)
            if index.isValid():
                tree.setCurrentIndex(index)

    def update_status_bar(self):
        """Update status bar with current selection info."""
        # Use debouncing to avoid excessive updates
        self._debounce_timer.stop()
        self._debounce_timer.start(100)  # 100ms delay

    def _do_update_status_bar(self):
        """Actually perform the status bar update."""
        selected_items = self.file_view.get_selected_items()
        self.status_bar.update_selection_info(selected_items, self.current_path)
        
    def _add_extra_file_actions(self, menu, file_path):
        """Hook for subclasses to add extra context-menu actions for files."""
        pass

    def set_clipboard(self, file_paths: List[Path], cut: bool = False):
        """Place file paths on the clipboard, optionally marked as a cut operation."""
        if not file_paths:
            return
        mime_data = QMimeData()
        mime_data.setUrls([QUrl.fromLocalFile(str(path)) for path in file_paths])
        if cut:
            mime_data.setData(self.CUT_MIME_TYPE, b'1')
        QApplication.clipboard().setMimeData(mime_data)

    def paste_from_clipboard(self, target_dir: Path = None):
        """Paste clipboard files/folders into the target directory (defaults to current path)."""
        mime_data = QApplication.clipboard().mimeData()
        if not mime_data.hasUrls():
            return

        target = Path(target_dir) if target_dir else self.current_path
        if not target.is_dir():
            target = target.parent

        is_cut = bytes(mime_data.data(self.CUT_MIME_TYPE)) == b'1'
        errors = []
        for url in mime_data.urls():
            src = Path(url.toLocalFile())
            try:
                if not src.exists():
                    continue
                # Prevent pasting a folder into itself or its own subfolder
                if src == target or (src.is_dir() and str(target).startswith(str(src) + os.sep)):
                    errors.append(f"{src.name}: cannot paste a folder into itself")
                    continue

                dest = target / src.name
                if is_cut:
                    if dest == src:
                        continue
                    if dest.exists():
                        errors.append(f"{src.name}: destination already exists")
                        continue
                    shutil.move(str(src), str(dest))
                else:
                    if dest.exists():
                        dest = self._get_unique_copy_path(target, src.name)
                    if src.is_dir():
                        shutil.copytree(str(src), str(dest))
                    else:
                        shutil.copy2(str(src), str(dest))
            except Exception as e:
                errors.append(f"{src.name}: {str(e)}")

        if is_cut:
            # A cut can only be pasted once
            QApplication.clipboard().clear()

        if errors:
            display_message("Some items could not be pasted:\n" + "\n".join(errors), "Paste Errors")

        self.refresh_views()

    @staticmethod
    def _get_unique_copy_path(target: Path, name: str) -> Path:
        """Generate a non-conflicting destination path like 'name (copy).ext'."""
        stem, suffix = os.path.splitext(name)
        candidate = target / f"{stem} (copy){suffix}"
        counter = 2
        while candidate.exists():
            candidate = target / f"{stem} (copy {counter}){suffix}"
            counter += 1
        return candidate

    def refresh_views(self):
        """Refresh both the file view and the navigation tree."""
        self.file_view.refresh()

    def show_context_menu_for_path(self, view: QWidget, position: QPoint, index: QModelIndex = None):
        """Shared context menu handler for both FileView and NavigationPanel."""
        menu = QMenu(view)

        # Get file path from the appropriate model based on the view
        if index and index.isValid():
            # Check if view is from NavigationPanel (uses QFileSystemModel) or FileView (uses LazyFileSystemModel)
            if view == self.nav_panel.dir_tree:
                file_path = Path(self.nav_panel.dir_model.filePath(index))
                selected_paths = self.nav_panel.get_selected_paths()
            else:
                file_path = Path(self.file_view.file_model.filePath(index))
                selected_paths = self.file_view.get_selected_items()

            # Operate on the whole selection if the clicked item is part of it
            if file_path in selected_paths and len(selected_paths) > 1:
                target_paths = selected_paths
            else:
                target_paths = [file_path]

            if file_path.is_file():
                open_action = menu.addAction("Open")
                open_action.triggered.connect(lambda: self.open_file(file_path))
                self._add_extra_file_actions(menu, file_path)

            for extension in self.extensions:
                extension.add_context_actions(menu, target_paths)

            rename_action = menu.addAction("Rename")
            rename_action.triggered.connect(lambda: self.file_view.rename_item(file_path))

            menu.addSeparator()

            copy_action = menu.addAction("Copy")
            copy_action.triggered.connect(lambda: self.file_view.copy_items(target_paths))

            cut_action = menu.addAction("Cut")
            cut_action.triggered.connect(lambda: self.file_view.cut_items(target_paths))

            if file_path.is_dir():
                paste_action = menu.addAction("Paste Into")
                paste_action.setEnabled(QApplication.clipboard().mimeData().hasUrls())
                paste_action.triggered.connect(lambda: self.paste_from_clipboard(file_path))

            select_all_action = menu.addAction("Select All")
            select_all_action.triggered.connect(view.selectAll)

            menu.addSeparator()

            delete_action = menu.addAction("Delete")
            delete_action.triggered.connect(lambda: self.file_view.delete_items(target_paths))

            menu.addSeparator()

            properties_action = menu.addAction("Properties")
            properties_action.triggered.connect(lambda: self.file_view.show_properties(file_path))

        else:
            # Background (empty area)
            paste_action = menu.addAction("Paste")
            paste_action.setEnabled(QApplication.clipboard().mimeData().hasUrls())
            paste_action.triggered.connect(lambda: self.paste_from_clipboard(self.current_path))

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
            self.tab_widget.tabBarDoubleClicked.connect(self.pin_tab)
            self.tab_widget.currentChanged.connect(
                lambda: QTimer.singleShot(0, self.on_current_changed))

            self.recent_files = parent.RecentFiles(parent)

            self.stack = QStackedWidget()
            self.stack.addWidget(self.recent_files)
            self.stack.addWidget(self.tab_widget)
            self.layout.addWidget(self.stack)

        def on_current_changed(self):
            has_tabs = self.tab_widget.count() > 0
            self.stack.setCurrentWidget(
                self.tab_widget if has_tabs else self.recent_files)
            self.parent.defer_update_page_map()

        @staticmethod
        def get_ext_studios():
            """Map each lowercase file extension to the studio that opens it."""
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
            return ext_studios

        def set_filepath(self, filepath: str):
            """Open a file in a tab, or focus existing tab."""
            # Check if already open
            if filepath in self.open_files:
                index = self.tab_widget.indexOf(self.open_files[filepath])
                if index >= 0:
                    self.tab_widget.setCurrentIndex(index)
                    return

            ext = os.path.splitext(filepath)[1].lower().lstrip('.')
            studio_class = self.get_ext_studios().get(ext)
            if not studio_class:
                return

            for index in reversed(range(self.tab_widget.count())):
                if self.tab_widget.tabBar().tabData(index):
                    self.close_tab(index)

            # Create studio and open file
            studio = studio_class(self)
            studio.open_file(filepath)
            tab_index = self.tab_widget.addTab(studio, '')
            tab_bar = self.tab_widget.tabBar()
            label = QLabel(os.path.basename(filepath), tab_bar)
            font = label.font()
            font.setItalic(True)
            label.setFont(font)
            label.setAttribute(Qt.WA_TransparentForMouseEvents)
            tab_bar.setTabButton(tab_index, QTabBar.LeftSide, label)
            tab_bar.setTabData(tab_index, True)
            self.tab_widget.setCurrentIndex(tab_index)
            self.open_files[filepath] = studio
            if hasattr(studio, 'modified'):
                studio.modified.connect(
                    lambda: self.pin_tab(self.tab_widget.indexOf(studio)))
            if hasattr(studio, 'close_requested'):
                studio.close_requested.connect(
                    lambda: self.close_tab(self.tab_widget.indexOf(studio)))

        def pin_tab(self, index):
            """Make the preview tab permanent."""
            tab_bar = self.tab_widget.tabBar()
            if not tab_bar.tabData(index):
                return
            tab_bar.setTabData(index, None)
            studio = self.tab_widget.widget(index)
            tab_bar.tabButton(index, QTabBar.LeftSide).deleteLater()
            tab_bar.setTabButton(index, QTabBar.LeftSide, None)
            filepath = next(
                fp for fp, w in self.open_files.items() if w is studio)
            self.tab_widget.setTabText(index, os.path.basename(filepath))

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
            widget.deleteLater()

        def load(self):
            pass

    class RecentFiles(QWidget):
        """Recently modified files under the root, shown when no file is open."""
        def __init__(self, parent):
            super().__init__(parent)
            self.parent = parent
            self.layout = CVBoxLayout(self)

            self.title = QLabel('Recent files')
            self.title.setObjectName('fileTreeRecentTitle')
            self.layout.addWidget(self.title)

            self.tree = QTreeWidget()
            self.tree.setColumnCount(3)
            self.tree.setHeaderHidden(True)
            self.tree.setRootIsDecorated(False)
            self.tree.setUniformRowHeights(True)
            self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeToContents)
            self.tree.header().setSectionResizeMode(1, QHeaderView.Stretch)
            self.tree.header().setSectionResizeMode(2, QHeaderView.ResizeToContents)
            self.tree.itemClicked.connect(self.open_item)
            self.layout.addWidget(self.tree)

            self.icon_provider = QFileIconProvider()

        def showEvent(self, event):
            super().showEvent(event)
            if not event.spontaneous():
                self.refresh()

        def open_item(self, item):
            path = item.data(0, Qt.UserRole)
            self.parent.set_current_file(path)
            QTimer.singleShot(0, lambda: self.parent.navigate_to(path))

        @staticmethod
        def time_ago(mtime: float) -> str:
            seconds = int(datetime.now().timestamp() - mtime)
            for unit, size in (('day', 86400), ('hour', 3600), ('min', 60)):
                if seconds >= size:
                    count = seconds // size
                    if unit == 'day' and count > 30:
                        return datetime.fromtimestamp(mtime).strftime('%d %b %Y')
                    return f"{count} {unit}{'s' if count > 1 else ''} ago"
            return 'just now'

        @qasync.asyncSlot()
        async def refresh(self):
            root = Path(self.parent.root_directory)
            extensions = set(self.parent.file_preview.get_ext_studios())
            files = await asyncio.to_thread(scan_recent_files, root, extensions)
            if not shiboken6.isValid(self.tree):
                return

            self.tree.clear()
            self.title.setText('Recent files' if files else 'No recent files')
            for mtime, path in files:
                path = Path(path)
                folder = path.parent.relative_to(root)
                item = QTreeWidgetItem([
                    path.name,
                    '' if folder == Path('.') else str(folder),
                    self.time_ago(mtime),
                ])
                item.setIcon(0, self.icon_provider.icon(QFileInfo(str(path))))
                item.setToolTip(0, str(path))
                item.setData(0, Qt.UserRole, path)
                self.tree.addTopLevelItem(item)

    class FindInFiles(QWidget):
        """Text search across files under the root, shown in place of the
        directory tree."""
        def __init__(self, parent):
            super().__init__(parent)
            self.parent = parent
            self.layout = CVBoxLayout(self)

            self.query_field = QLineEdit()
            self.query_field.setPlaceholderText('Find in files...')
            self.layout.addWidget(self.query_field)

            self.summary = QLabel()
            self.layout.addWidget(self.summary)

            self.tree = QTreeWidget()
            self.tree.setHeaderHidden(True)
            self.tree.setUniformRowHeights(True)
            self.tree.setIndentation(10)
            self.tree.itemClicked.connect(self.open_item)
            self.layout.addWidget(self.tree)

            self.icon_provider = QFileIconProvider()

            self._search_timer = QTimer(self)
            self._search_timer.setSingleShot(True)
            self._search_timer.setInterval(300)
            self._search_timer.timeout.connect(self.search)
            self.query_field.textChanged.connect(self._search_timer.start)
            self.query_field.returnPressed.connect(self.search)

        @qasync.asyncSlot()
        async def search(self):
            self._search_timer.stop()
            query = self.query_field.text()
            if not query:
                self.tree.clear()
                self.summary.clear()
                return

            root = Path(self.parent.root_directory)
            results = await asyncio.to_thread(
                search_in_files, root, query, self.parent.show_hidden)
            if not shiboken6.isValid(self.tree) or query != self.query_field.text():
                return

            self.tree.clear()
            match_count = sum(len(matches) for _, matches in results)
            self.summary.setText(
                f'{match_count} results in {len(results)} files'
                if results else 'No results')
            for path, matches in results:
                file_item = QTreeWidgetItem([
                    f'{path.name}  {path.parent.relative_to(root)}'
                ])
                file_item.setIcon(0, self.icon_provider.icon(QFileInfo(str(path))))
                file_item.setToolTip(0, str(path))
                file_item.setData(0, Qt.UserRole, (path, None))
                for line_no, line in matches:
                    match_item = QTreeWidgetItem([f'{line_no}: {line}'])
                    match_item.setToolTip(0, line)
                    match_item.setData(0, Qt.UserRole, (path, line_no))
                    file_item.addChild(match_item)
                self.tree.addTopLevelItem(file_item)
                file_item.setExpanded(True)

        def open_item(self, item):
            path, line_no = item.data(0, Qt.UserRole)
            self.parent.set_current_file(path)
            studio = self.parent.file_preview.open_files.get(str(path))
            editor = getattr(studio, 'editor', None)
            if editor and line_no:
                block = editor.document().findBlockByNumber(line_no - 1)
                editor.setTextCursor(QTextCursor(block))
                editor.centerCursor()

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

            self.new_folder_btn = IconButton(
                parent=self,
                icon_path=":/resources/icon-new-folder.png",
                tooltip="New Folder"
            )
            self.new_folder_btn.clicked.connect(self.create_new_folder)

            self.options_menu = CustomMenu(parent=self, schema=[{
                'text': 'Options',
                'icon_path': ':/resources/icon-dots.png',
                'submenu': lambda: [{
                    'text': 'Show Files in Tree',
                    'checkable': True,
                    'checked_state': lambda: self.parent.files_in_tree,
                    'target': lambda: self.toggle_files_in_tree(),
                }, {
                    'text': 'Show Hidden Files',
                    'checkable': True,
                    'checked_state': lambda: self.parent.show_hidden,
                    'target': self.set_show_hidden,
                }, *(
                    item for extension in self.parent.extensions
                    for item in extension.options_menu_schema()
                ), {
                    'type': 'separator',
                }, {
                    'text': 'Find in Files',
                    'checkable': True,
                    'checked_state': lambda: not self.find_in_files.isHidden(),
                    'target': self.set_find_in_files_visible,
                }],
            }])
            self.options_menu.create_toolbar()

            toolbar_row.addWidget(self.back_btn)
            toolbar_row.addWidget(self.forward_btn)
            toolbar_row.addWidget(self.up_btn)
            toolbar_row.addStretch()
            for extension in self.parent.extensions:
                toolbar_row.addWidget(extension)
            toolbar_row.addWidget(self.new_folder_btn)
            toolbar_row.addWidget(self.options_menu)
            self.layout.addLayout(toolbar_row)

            # Search field
            self.search_field = QLineEdit()
            self.search_field.setPlaceholderText("Search files...")
            self.search_field.textChanged.connect(self.parent.file_view.filter_items)
            self.layout.addWidget(self.search_field)

            if self.parent.show_bookmarks:
                # Bookmarks section
                bookmarks_label = QLabel("Bookmarks")
                bookmarks_label.setObjectName('fileTreeBookmarksLabel')

                # Directory tree section
                tree_label = QLabel("Computer")
                tree_label.setObjectName('fileTreeComputerLabel')

            # Bookmarks list
            self.bookmarks_list = QListWidget()
            self.bookmarks_list.itemClicked.connect(self.on_bookmark_clicked)

            # Directory tree
            self.dir_tree = QTreeView()
            self.dir_tree.setHeaderHidden(True)
            self.dir_tree.setUniformRowHeights(True)  # Performance optimization
            self.dir_model = ColoredFileSystemModel(self.parent.item_color)
            if self.parent.media_thumbnails:
                self.icon_provider = ThumbnailIconProvider()
                self.dir_model.setIconProvider(self.icon_provider)
            # Disable features that slow down large directories
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
            self.dir_tree.setSelectionMode(QAbstractItemView.ExtendedSelection)

            # Keyboard shortcuts for copy / cut / paste
            copy_shortcut = QShortcut(QKeySequence.Copy, self.dir_tree, context=Qt.WidgetShortcut)
            copy_shortcut.activated.connect(lambda: self.parent.set_clipboard(self.get_selected_paths(), cut=False))
            cut_shortcut = QShortcut(QKeySequence.Cut, self.dir_tree, context=Qt.WidgetShortcut)
            cut_shortcut.activated.connect(lambda: self.parent.set_clipboard(self.get_selected_paths(), cut=True))
            paste_shortcut = QShortcut(QKeySequence.Paste, self.dir_tree, context=Qt.WidgetShortcut)
            paste_shortcut.activated.connect(self.paste_into_selected)
            delete_shortcut = QShortcut(QKeySequence.Delete, self.dir_tree, context=Qt.WidgetShortcut)
            delete_shortcut.activated.connect(lambda: self.parent.file_view.delete_items(self.get_selected_paths()))

            # Hide columns except name
            for i in range(1, self.dir_model.columnCount()):
                self.dir_tree.hideColumn(i)

            self.dir_tree.selectionModel().currentChanged.connect(
                self.on_tree_current_changed)

            # Add splitter between bookmarks and directory tree
            from PySide6.QtWidgets import QSplitter, QWidget, QVBoxLayout

            self.splitter = QSplitter(Qt.Vertical)

            # Directory tree widget container
            dir_tree_widget = QWidget()
            dir_tree_layout = CVBoxLayout(dir_tree_widget)
            if self.parent.show_bookmarks:
                dir_tree_layout.addWidget(tree_label)
            dir_tree_layout.addWidget(self.dir_tree)
            self.find_in_files = self.parent.FindInFiles(self.parent)
            self.find_in_files.hide()
            dir_tree_layout.addWidget(self.find_in_files)
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
            self.update_dir_filter()
            self.populate_bookmarks()

        def update_dir_filter(self):
            entries = QDir.AllEntries if self.parent.files_in_tree else QDir.Dirs
            hidden = QDir.Hidden if self.parent.show_hidden else QDir.Filter(0)
            self.dir_model.setFilter(entries | QDir.NoDotAndDotDot | hidden)

        def set_show_hidden(self, show: bool):
            self.parent.show_hidden = show
            self.parent.file_view.file_model.show_hidden = show
            self.update_dir_filter()
            self.parent.file_view.refresh()

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

        def on_tree_current_changed(self, current: QModelIndex, _previous):
            """Open what the tree's current item points to, by mouse or keyboard."""
            if not current.isValid():
                return
            path = Path(self.dir_model.filePath(current))
            if not path.is_dir():
                self.parent.set_current_file(path)
            elif not self.parent.files_in_tree and path != self.parent.current_path:
                self.location_changed.emit(path)

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

        def get_selected_paths(self) -> List[Path]:
            """Get the paths currently selected in the directory tree."""
            indexes = self.dir_tree.selectionModel().selectedIndexes()
            return [Path(self.dir_model.filePath(idx)) for idx in indexes if idx.column() == 0]

        def paste_into_selected(self):
            """Paste clipboard items into the selected folder, or the current path."""
            selected = self.get_selected_paths()
            if len(selected) == 1 and selected[0].is_dir():
                target = selected[0]
            else:
                target = self.parent.current_path
            self.parent.paste_from_clipboard(target)

        def set_find_in_files_visible(self, visible: bool):
            self.dir_tree.setVisible(not visible)
            self.find_in_files.setVisible(visible)
            if visible:
                self.find_in_files.query_field.setFocus()
                self.find_in_files.query_field.selectAll()

        def toggle_files_in_tree(self):
            """Toggle the files_in_tree setting and refresh the navigation panel."""
            self.parent.files_in_tree = not self.parent.files_in_tree
            self.update_dir_filter()

            if self.parent.files_in_tree:
                self.parent.file_view_container.hide()
            else:
                self.parent.file_view_container.show()

            self.parent.navigate_to(self.parent.current_path, add_to_history=False)

        def create_new_folder(self):
            """Create a new folder in the current directory."""
            name, ok = get_text(
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
            self.file_model = LazyFileSystemModel(
                self, media_thumbnails=self.parent.media_thumbnails
            )
            self.file_model.show_hidden = self.parent.show_hidden
            self.file_model.color_for = self.parent.item_color

            self.watcher = QFileSystemWatcher(self)
            self._watch_timer = QTimer(self)
            self._watch_timer.setSingleShot(True)
            self._watch_timer.setInterval(300)
            self._watch_timer.timeout.connect(self.on_directory_changed)
            self.watcher.directoryChanged.connect(self._watch_timer.start)

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
                view.setSelectionMode(QAbstractItemView.ExtendedSelection)
                view.setDragDropMode(QAbstractItemView.DragDrop)
                view.setDefaultDropAction(Qt.MoveAction)

            # Keyboard shortcuts for copy / cut / paste
            for view in [self.detail_view, self.list_view, self.grid_view]:
                copy_shortcut = QShortcut(QKeySequence.Copy, view, context=Qt.WidgetShortcut)
                copy_shortcut.activated.connect(lambda: self.copy_items(self.get_selected_items()))
                cut_shortcut = QShortcut(QKeySequence.Cut, view, context=Qt.WidgetShortcut)
                cut_shortcut.activated.connect(lambda: self.cut_items(self.get_selected_items()))
                paste_shortcut = QShortcut(QKeySequence.Paste, view, context=Qt.WidgetShortcut)
                paste_shortcut.activated.connect(lambda: self.paste_items())
                delete_shortcut = QShortcut(QKeySequence.Delete, view, context=Qt.WidgetShortcut)
                delete_shortcut.activated.connect(lambda: self.delete_items(self.get_selected_items()))

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

            if self.watcher.directories():
                self.watcher.removePaths(self.watcher.directories())
            self.watcher.addPath(str(path))
            self.current_directory = path
            self.file_model.setRootPath(str(path))

        def on_directory_changed(self):
            view = self.get_current_view()
            selected = [p.name for p in self.get_selected_items()]
            scroll = view.verticalScrollBar().value()
            self.refresh()
            for name in selected:
                index = self.file_model.indexFromName(name)
                if index.isValid():
                    view.selectionModel().select(
                        index, QItemSelectionModel.Select | QItemSelectionModel.Rows)
            view.verticalScrollBar().setValue(scroll)
            self.parent.refresh_extensions()

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
            new_name, ok = get_text(
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
            self.parent.set_clipboard(file_paths, cut=False)

        def cut_items(self, file_paths: List[Path]):
            """Cut items to clipboard."""
            self.parent.set_clipboard(file_paths, cut=True)

        def paste_items(self, target_dir: Path = None):
            """Paste clipboard items into the target (or current) directory."""
            self.parent.paste_from_clipboard(target_dir or self.current_directory or self.parent.current_path)

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