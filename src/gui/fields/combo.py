from PySide6.QtGui import QStandardItem, QColor, Qt
from PySide6.QtWidgets import QComboBox, QInputDialog
from src.utils import sql

from src.utils.helpers import block_signals


class BaseCombo(QComboBox):
    def __init__(self, parent=None, **kwargs):
        super().__init__(parent)
        self.parent = parent
        self.items = kwargs.pop('items', None)
        self.query = kwargs.pop('query', None)
        self.table_name = kwargs.get('table_name', None)
        self.fetch_keys = kwargs.get('fetch_keys', ('name',))
        self.allow_new = kwargs.get('allow_new', False)
        self.items_have_keys = kwargs.get('items_have_keys', True)

        if self.table_name and not self.query and self.fetch_keys:
            self.query = f"""
                SELECT {', '.join(self.fetch_keys)}
                FROM {self.table_name}
                -- ORDER BY pinned DESC, ordr, name
            """

        self.setFixedHeight(25)
        self.setMaximumWidth(200)
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
        return self.itemData(self.currentIndex())

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
        # with block_signals(self):  # todo
        self.setCurrentIndex(index)

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