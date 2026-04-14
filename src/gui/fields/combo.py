from PySide6.QtCore import QSortFilterProxyModel
from PySide6.QtGui import QStandardItem, QColor, Qt
from PySide6.QtWidgets import (
    QApplication, QComboBox, QFrame, QInputDialog,
    QLabel, QLineEdit, QListView, QVBoxLayout,
)
from utils import sql

from utils.helpers import block_signals, set_module_type


class _HeaderAwareFilterProxy(QSortFilterProxyModel):
    """Keeps disabled (header) items visible regardless of filter text."""

    def filterAcceptsRow(self, source_row, source_parent):
        model = self.sourceModel()
        item = model.item(source_row)
        if item and not item.isEnabled():
            return True
        return super().filterAcceptsRow(source_row, source_parent)


class _FilterPopup(QFrame):
    """Popup with a filter text box and list view for BaseCombo."""

    def __init__(self, combo):
        super().__init__(combo, Qt.Popup | Qt.FramelessWindowHint)
        self.combo = combo
        self.setFrameShape(QFrame.NoFrame)

        from gui.style import PRIMARY_COLOR, TEXT_COLOR
        from utils.helpers import apply_alpha_to_hex
        border_color = apply_alpha_to_hex(TEXT_COLOR, 0.3)
        self.setStyleSheet(
            f"_FilterPopup {{ background-color: {PRIMARY_COLOR};"
            f" border: 1px solid {border_color}; }}"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(2)

        self.pinned_index = getattr(combo, 'pinned_index', None)

        self.filter_edit = QLineEdit(self)
        self.filter_edit.setPlaceholderText('Filter...')
        if combo.count() > 20:
            layout.addWidget(self.filter_edit)
        else:
            self.filter_edit.hide()

        # Pinned item shown as a normal-looking single-row list
        if self.pinned_index is not None:
            self.pinned_view = QListView(self)
            self.pinned_view.setModel(combo.model())
            self.pinned_view.setRootIndex(combo.model().index(
                self.pinned_index, 0).parent())
            # Hide all rows except the pinned one
            for i in range(combo.model().rowCount()):
                if i != self.pinned_index:
                    self.pinned_view.setRowHidden(i, True)
            self.pinned_view.setFixedHeight(
                self.pinned_view.sizeHintForRow(0) + 2)
            self.pinned_view.setVerticalScrollBarPolicy(
                Qt.ScrollBarAlwaysOff)
            self.pinned_view.setHorizontalScrollBarPolicy(
                Qt.ScrollBarAlwaysOff)
            self.pinned_view.clicked.connect(
                lambda idx: self._select(idx.row()))
            layout.addWidget(self.pinned_view)

        self.proxy = _HeaderAwareFilterProxy(self)
        self.proxy.setSourceModel(combo.model())
        self.proxy.setFilterCaseSensitivity(Qt.CaseInsensitive)
        self.proxy.setFilterRole(Qt.DisplayRole)

        self.list_view = QListView(self)
        self.list_view.setModel(self.proxy)
        # Hide pinned row from the filtered list
        if self.pinned_index is not None:
            proxy_idx = self.proxy.mapFromSource(
                combo.model().index(self.pinned_index, 0))
            if proxy_idx.isValid():
                self.list_view.setRowHidden(proxy_idx.row(), True)
        layout.addWidget(self.list_view)

        self.filter_edit.textChanged.connect(self._on_filter_changed)
        self.list_view.clicked.connect(self._on_item_clicked)

    def _on_filter_changed(self, text):
        self.proxy.setFilterFixedString(text)
        # Re-hide the pinned row after filter changes
        if self.pinned_index is not None:
            proxy_idx = self.proxy.mapFromSource(
                self.combo.model().index(self.pinned_index, 0))
            if proxy_idx.isValid():
                self.list_view.setRowHidden(proxy_idx.row(), True)

    def _select(self, source_row):
        self.combo.setCurrentIndex(source_row)
        self.close()

    def _on_item_clicked(self, proxy_index):
        source_index = self.proxy.mapToSource(proxy_index)
        item = self.combo.model().itemFromIndex(source_index)
        if item and not item.isEnabled():
            return
        self._select(source_index.row())

    def show_below(self, widget):
        """Position and show the popup below (or above) the widget."""
        screen = QApplication.screenAt(widget.mapToGlobal(
            widget.rect().center()))
        if screen is None:
            screen = QApplication.primaryScreen()
        screen_rect = screen.availableGeometry()
        max_h = int(screen_rect.height() * 0.8)

        pos = widget.mapToGlobal(widget.rect().bottomLeft())
        available_h = screen_rect.bottom() - pos.y()
        self.resize(max(widget.width(), 200), min(max_h, available_h))
        self.move(pos)
        self.show()
        self.filter_edit.setFocus()
        self.filter_edit.clear()

        # Highlight current combo selection in the list
        current = self.combo.currentIndex()
        proxy_idx = self.proxy.mapFromSource(
            self.combo.model().index(current, 0))
        if proxy_idx.isValid():
            self.list_view.setCurrentIndex(proxy_idx)


@set_module_type('Fields')
class BaseCombo(QComboBox):
    def __init__(self, parent=None, **kwargs):
        super().__init__(parent)
        self.parent = parent
        self._filter_popup = None
        self.pinned_index = kwargs.pop('pinned_index', None)
        self.items = kwargs.pop('items', None)
        self.query = kwargs.pop('query', None)
        self.table_name = kwargs.get('table_name', None)
        self.fetch_keys = kwargs.get('fetch_keys', ('name',))
        self.allow_new = kwargs.get('allow_new', False)
        self.items_have_keys = kwargs.get('items_have_keys', True)
        self.value_type = kwargs.get('value_type', None)
        width = kwargs.get('width', 150)

        self.setFixedWidth(width)

        if self.table_name and not self.query and self.fetch_keys:
            self.query = f"""
                SELECT {', '.join(self.fetch_keys)}
                FROM {self.table_name}
                -- ORDER BY pinned DESC, ordr, name
            """

        self.setFixedHeight(18)
        self.setMaximumWidth(200)
        self.load()
        self.currentIndexChanged.connect(self.on_index_changed)

    def showPopup(self):
        if self._filter_popup and self._filter_popup.isVisible():
            self._filter_popup.close()
        self._filter_popup = _FilterPopup(self)
        self._filter_popup.show_below(self)

    def hidePopup(self):
        if self._filter_popup and self._filter_popup.isVisible():
            self._filter_popup.close()
        super().hidePopup()

    def wheelEvent(self, event):
        event.ignore()

    def load(self):
        with block_signals(self):
            self.clear()
            if self.items:
                # If items are provided, use them directly
                try:
                    if isinstance(self.items, dict):
                        for key, value in self.items.items():
                            self.addItem(value, key)
                    else:
                        for item in self.items:
                            self.addItem(item, item)
                except Exception as e:
                    raise e
            elif self.query:
                # If a query is provided, fetch items from the database
                results = sql.get_results(self.query)
                for result in results:
                    if len(self.fetch_keys) == 1:
                        self.addItem(result[0], result[0])
                    elif len(self.fetch_keys) > 1:
                        self.addItem(result[0], result[1])

            if self.allow_new:
                self.addItem('< New >', '<NEW>')

            # roles = sql.get_results("SELECT name FROM roles", return_type='list')
            # for role in roles:
            #     self.addItem(role.title(), role)
            # # add a 'New Role' option
            # self.addItem('< New >', '<NEW>')

    def last_item(self):
        if self.model().rowCount() == 0:
            return None
        last_item = self.model().item(self.model().rowCount() - 1)
        return last_item

    def get_value(self):
        if self.currentIndex() == -1:
            return None
        value = self.itemData(self.currentIndex())
        if self.value_type and value is not None:
            try:
                value = self.value_type(value)
            except (ValueError, TypeError):
                pass
        return value

    def set_value(self, key):  # todo rename
        index = self.findData(key) if self.items_have_keys else self.findText(key)
        if index == -1:
            # Try the opposite search method as fallback
            index = self.findText(key) if self.items_have_keys else self.findData(key)
        if index == -1:
            last_item = self.last_item()
            if last_item:
                # Create a new item with the missing model key and set its color to red, and set the data to the model key
                item = QStandardItem(str(key))
                item.setForeground(QColor('red'))
                if self.items_have_keys:
                    item.setData(key, Qt.UserRole)
                self.model().appendRow(item)
                self.setCurrentIndex(self.model().rowCount() - 1)
                return
        self.setCurrentIndex(index)

    def addItem(self, text, data=None):
        if data is None:
            super().addItem(str(text))
        else:
            super().addItem(str(text), data)

    # def addItem(self, *args):
    #     with block_signals(self):
    #         super().addItem(*args)
    #
    # def addItems(self, texts):  # todo clean
    #     with block_signals(self):
    #         super().addItems(texts)

    def on_index_changed(self, index):
        if self.itemData(index) == '<NEW>':
            new_name, ok = QInputDialog.getText(self, "New Item", "Enter the name for the new item:")
            if ok and new_name:
                sql.execute(f"INSERT INTO `{self.table_name}` (name) VALUES (?)", (new_name,))  # .lower(),))

                self.load()

                new_index = self.findText(new_name)  # .title())
                if new_index != -1:
                    self.setCurrentIndex(new_index)
            else:
                # If dialog was cancelled or empty input, revert to previous selection
                self.setCurrentIndex(self.findData('<NEW>') - 1)
        if self.parent:
            self.parent.update_config()