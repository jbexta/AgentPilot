import os

from PySide6.QtCore import QSize, QTimer, QUrl
from PySide6.QtGui import QDrag, QIcon, QImageReader, QPixmap, Qt
from PySide6.QtWidgets import QAbstractItemView, QListView, QListWidget, QListWidgetItem, QMenu, QWidget

from gui.gui_utils.layouts import CVBoxLayout
from gui.gui_utils.helpers import colorize_pixmap


class MediaIconListWidget(QListWidget):
    """Icon-mode list of media files that drags items out as file URLs.

    Images show their own thumbnail, other media show their type icon.
    Pass ``on_delete(filepath)`` to enable a Delete context menu entry."""

    def __init__(self, parent=None, icon_size=48, on_delete=None):
        super().__init__(parent)
        self.on_delete = on_delete
        self.setViewMode(QListView.IconMode)
        self.setMovement(QListView.Static)
        self.setResizeMode(QListView.Adjust)
        self.setIconSize(QSize(icon_size, icon_size))
        self.setWrapping(True)
        self.setSpacing(4)
        self.setDragEnabled(True)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setMouseTracking(True)
        self._hover_item = None
        self._hover_popup = None
        self._hover_preview = None
        self._hover_timer = QTimer(self)
        self._hover_timer.setSingleShot(True)
        self._hover_timer.setInterval(120)
        self._hover_timer.timeout.connect(self._on_hover_timeout)
        if on_delete:
            self.setContextMenuPolicy(Qt.CustomContextMenu)
            self.customContextMenuRequested.connect(self._show_context_menu)

    _icon_cache = {}  # (filepath, mtime) -> QIcon

    def _file_icon(self, filepath):
        from utils.media import IMAGE_EXTS, get_media_icon_path
        ext = os.path.splitext(filepath)[1].lower()
        if ext not in IMAGE_EXTS:
            return QIcon(colorize_pixmap(QPixmap(get_media_icon_path(ext=ext))))

        try:
            cache_key = (filepath, os.path.getmtime(filepath))
        except OSError:
            cache_key = (filepath, None)
        icon = self._icon_cache.get(cache_key)
        if icon is None:
            # Decode pre-scaled: full-resolution decodes of large generated
            # images freeze the UI on every reload.
            reader = QImageReader(filepath)
            size = reader.size()
            max_dim = self.iconSize().width() * 2
            if size.isValid() and (size.width() > max_dim or size.height() > max_dim):
                reader.setScaledSize(size.scaled(max_dim, max_dim, Qt.KeepAspectRatio))
            icon = QIcon(QPixmap.fromImage(reader.read()))
            self._icon_cache[cache_key] = icon
        return icon

    def load_files(self, filepaths, ids=None):
        self._close_hover_popup()
        self.clear()
        for i, filepath in enumerate(filepaths):
            item = QListWidgetItem(self._file_icon(filepath), '')
            item.setData(Qt.UserRole, filepath)
            if ids:
                item.setData(Qt.UserRole + 1, ids[i])
            item.setToolTip(os.path.basename(filepath))
            self.addItem(item)

    def mimeData(self, items):
        mime_data = super().mimeData(items)
        urls = [QUrl.fromLocalFile(item.data(Qt.UserRole)) for item in items
                if item.data(Qt.UserRole)]
        if urls:
            mime_data.setUrls(urls)
        return mime_data

    def startDrag(self, supported_actions):
        self._close_hover_popup()
        items = self.selectedItems()
        if not items:
            return
        drag = QDrag(self)
        drag.setMimeData(self.mimeData(items))
        drag.exec_(Qt.CopyAction)

    def _show_context_menu(self, position):
        item = self.itemAt(position)
        if item is None:
            return
        menu = QMenu(self)
        menu.addAction('Delete').triggered.connect(
            lambda: self.on_delete(item.data(Qt.UserRole)))
        menu.exec_(self.mapToGlobal(position))

    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)
        if event.buttons():
            self._close_hover_popup()
            return
        item = self.itemAt(event.pos())
        if item is self._hover_item:
            return
        # Debounced: creating a media player per hovered item exhausts
        # multimedia resources when sweeping across the list.
        self._close_hover_popup()
        if item is not None:
            self._hover_item = item
            self._hover_timer.start()

    def _on_hover_timeout(self):
        if self._hover_item is not None and self._hover_popup is None:
            self._show_hover_popup(self._hover_item)

    def leaveEvent(self, event):
        super().leaveEvent(event)
        self._close_hover_popup()

    def _show_hover_popup(self, item):
        from utils.media import get_media_preview_class, get_media_type_from_ext
        filepath = item.data(Qt.UserRole)
        if not filepath or not os.path.isfile(filepath):
            return
        ext = os.path.splitext(filepath)[1].lower()
        if get_media_type_from_ext(ext) not in ('image', 'video'):
            return
        preview_class = get_media_preview_class(ext=ext)
        if preview_class is None:
            return

        popup = QWidget(None)
        popup.setWindowFlags(
            Qt.ToolTip | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        popup.setAttribute(Qt.WA_ShowWithoutActivating)
        popup.setFixedSize(320, 240)
        popup_layout = CVBoxLayout(popup)
        preview = preview_class(popup)
        preview.set_filepath(filepath)
        popup_layout.addWidget(preview)

        rect = self.visualItemRect(item)
        global_pos = self.viewport().mapToGlobal(rect.topLeft())
        px = global_pos.x() + (rect.width() - popup.width()) // 2
        py = global_pos.y() - popup.height() - 4
        if py < 0:
            py = global_pos.y() + rect.height() + 4
        popup.move(px, py)
        popup.show()
        self._hover_popup = popup
        self._hover_preview = preview

    def _close_hover_popup(self):
        self._hover_timer.stop()
        self._hover_item = None
        if self._hover_preview is not None:
            if hasattr(self._hover_preview, 'cleanup'):
                self._hover_preview.cleanup()
            self._hover_preview = None
        if self._hover_popup is not None:
            self._hover_popup.close()
            self._hover_popup.deleteLater()
            self._hover_popup = None
