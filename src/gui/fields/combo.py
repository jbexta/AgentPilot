from PySide6.QtGui import QStandardItem, QColor, Qt
from PySide6.QtWidgets import QComboBox, QInputDialog
from src.utils import sql

from src.utils.helpers import block_signals


class Combo(QComboBox):
    def __init__(self, parent=None, **kwargs):
        super().__init__(parent)
        # self.items_have_keys = True
        self.items = kwargs.get('items', None)
        self.query = kwargs.get('query', None)
        self.table_name = kwargs.get('table_name', None)
        self.fetch_keys = kwargs.get('fetch_keys', ('name',))
        self.allow_new = kwargs.get('allow_new', False)

        if self.table_name and not self.query and self.fetch_keys:
            self.query = f"""
                SELECT {', '.join(self.fetch_keys)}
                FROM {self.table_name}
                -- ORDER BY pinned DESC, ordr, name
            """

        self.setFixedHeight(25)
        self.load()
        self.currentIndexChanged.connect(self.on_index_changed)

    def load(self):
        with block_signals(self):
            self.clear()
            if self.items:
                # If items are provided, use them directly
                if isinstance(self.items, dict):
                    for key, value in self.items.items():
                        self.addItem(value, key)
                else:
                    for item in self.items:
                        self.addItem(item, item)
            elif self.query:
                # If a query is provided, fetch items from the database
                results = sql.get_results(self.query)
                for result in results:
                    if len(result) == 1:
                        self.addItem(result[0], result[0])
                    elif len(result) > 1:
                        self.addItem(result[1], result[0])

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

    def set_value(self, key):  # todo rename
        # items_have_keys =
        index = self.findData(key)  # if self.items_have_keys else self.findText(key)
        if index == -1:
            last_item = self.last_item()
            if last_item:
                # Create a new item with the missing model key and set its color to red, and set the data to the model key
                item = QStandardItem(key)
                item.setForeground(QColor('red'))
                if self.items_have_keys:
                    item.setData(key, Qt.UserRole)
                self.model().appendRow(item)
                self.setCurrentIndex(self.model().rowCount() - 1)
                return
        self.setCurrentIndex(index)

    def get_value(self):
        if self.currentIndex() == -1:
            return None
        return self.itemData(self.currentIndex())

    def on_index_changed(self, index):
        if self.itemData(index) == '<NEW>':
            new_role, ok = QInputDialog.getText(self, "New Role", "Enter the name for the new role:")
            if ok and new_role:
                sql.execute("INSERT INTO roles (name) VALUES (?)", (new_role.lower(),))

                self.load()

                new_index = self.findText(new_role.title())
                if new_index != -1:
                    self.setCurrentIndex(new_index)
            else:
                # If dialog was cancelled or empty input, revert to previous selection
                self.setCurrentIndex(self.findData('<NEW>') - 1)
